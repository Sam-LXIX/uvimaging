#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <math.h>
#include <unistd.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/i2c_master.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"

// -----------------------------------------------------------------------------
// LOTUS UV-Cured Epoxy Fiber Splicer - ESP32-S3 hardware controller
// Raspberry Pi 5 <-> ESP32-S3: native USB Serial/JTAG console.
// Pin assignments match Nehal_Patel_UV_Splicer_Schem_PCB.
// ESP-IDF 5.4.x. No Arduino framework required.
// -----------------------------------------------------------------------------

#define FW_VERSION "1.2.4-s3-8mb"

// Motor control
#define PIN_X_STEP       4
#define PIN_X_DIR        5
#define PIN_Y_STEP       6
#define PIN_Y_DIR        7
#define PIN_Z_STEP      10
#define PIN_Z_DIR       11
#define PIN_X_ENABLE    12
#define PIN_Y_ENABLE    13
#define PIN_Z_ENABLE    14
#define PIN_X_FAULT     33
#define PIN_Y_FAULT     34
#define PIN_Z_FAULT     35

// Sensors / outputs
#define PIN_I2C_SDA       8
#define PIN_I2C_SCL       9
#define PIN_LED_CTRL     17
#define PIN_UV_DIM       18
#define PIN_FAN_PWM      21
#define PIN_FAN_TACH     40

// I2C addresses from schematic strapping
#define ADDR_INA260      0x40
#define ADDR_SHT41       0x44
#define ADDR_TMP75       0x48

// Motor command safety limits
#define MAX_MOVE_PULSES  20000
#define MIN_PPS          10
#define MAX_PPS          5000
#define STEP_HIGH_US     4

// Most 4-wire fans produce two tach pulses per revolution.
#define FAN_PULSES_PER_REV 2

// Fan automatic-control thresholds (PCB TMP75)
#define FAN_TEMP_1_C     35.0f
#define FAN_TEMP_2_C     45.0f
#define FAN_TEMP_3_C     55.0f

// PWM setup
#define PWM_MODE         LEDC_LOW_SPEED_MODE
#define PWM_TIMER_FAN    LEDC_TIMER_0
#define PWM_TIMER_AUX    LEDC_TIMER_1
#define PWM_CH_FAN       LEDC_CHANNEL_0
#define PWM_CH_UV        LEDC_CHANNEL_1
#define PWM_CH_LIGHT     LEDC_CHANNEL_2
#define FAN_PWM_HZ       25000
#define FAN_PWM_BITS     LEDC_TIMER_8_BIT
#define FAN_PWM_MAX      255
#define AUX_PWM_HZ       1000
#define PWM_BITS         LEDC_TIMER_10_BIT
#define PWM_MAX          1023
#define CAMERA_LIGHT_MAX_PERCENT 50.0f  // GPIO17 only; UV is independent

static SemaphoreHandle_t g_state_lock;
static QueueHandle_t g_motor_queue;

static volatile uint32_t g_motion_epoch = 0;
static volatile TickType_t g_last_host_tick = 0;
static volatile bool g_link_expired = false;
static volatile uint32_t g_tach_pulses = 0;

static bool g_motor_busy = false;
static int32_t g_pos_x = 0;
static int32_t g_pos_y = 0;
static int32_t g_pos_z = 0;

static float g_pcb_temp_c = NAN;
static float g_ambient_temp_c = NAN;
static float g_humidity_rh = NAN;
static float g_bus_voltage_v = NAN;
static float g_bus_current_ma = NAN;
static float g_bus_power_w = NAN;
static bool g_tmp75_ok = false;
static bool g_sht41_ok = false;
static bool g_ina260_ok = false;

static uint32_t g_fan_rpm = 0;
static int g_fan_percent = 100; // fail-safe until first valid TMP75 reading
static bool g_fan_auto = true;
static float g_light_percent = 12.5f;
static int g_uv_percent = 0;
static bool g_uv_armed = false;
static bool g_uv_active = false;
static int64_t g_uv_end_us = 0;

static i2c_master_bus_handle_t g_i2c_bus = NULL;
static i2c_master_dev_handle_t g_tmp75 = NULL;
static i2c_master_dev_handle_t g_sht41 = NULL;
static i2c_master_dev_handle_t g_ina260 = NULL;

typedef struct {
    char axis;
    int32_t pulses;
    uint32_t pps;
    uint32_t epoch;
} motor_cmd_t;

static inline void state_lock(void) {
    xSemaphoreTake(g_state_lock, portMAX_DELAY);
}

static inline void state_unlock(void) {
    xSemaphoreGive(g_state_lock);
}

static bool fault_active(int pin) {
    // DRV8825 FLT is active-low.
    return gpio_get_level(pin) == 0;
}

static int fault_pin_for_axis(char axis) {
    switch (axis) {
        case 'X': return PIN_X_FAULT;
        case 'Y': return PIN_Y_FAULT;
        case 'Z': return PIN_Z_FAULT;
        default: return -1;
    }
}

static int step_pin_for_axis(char axis) {
    switch (axis) {
        case 'X': return PIN_X_STEP;
        case 'Y': return PIN_Y_STEP;
        case 'Z': return PIN_Z_STEP;
        default: return -1;
    }
}

static int dir_pin_for_axis(char axis) {
    switch (axis) {
        case 'X': return PIN_X_DIR;
        case 'Y': return PIN_Y_DIR;
        case 'Z': return PIN_Z_DIR;
        default: return -1;
    }
}

static int enable_pin_for_axis(char axis) {
    switch (axis) {
        case 'X': return PIN_X_ENABLE;
        case 'Y': return PIN_Y_ENABLE;
        case 'Z': return PIN_Z_ENABLE;
        default: return -1;
    }
}

static int32_t *position_for_axis(char axis) {
    switch (axis) {
        case 'X': return &g_pos_x;
        case 'Y': return &g_pos_y;
        case 'Z': return &g_pos_z;
        default: return NULL;
    }
}

static void set_axis_enabled(char axis, bool enabled) {
    int pin = enable_pin_for_axis(axis);
    if (pin >= 0) {
        // DRV8825 ENBL is active-low.
        gpio_set_level(pin, enabled ? 0 : 1);
    }
}

static void disable_all_motors(void) {
    gpio_set_level(PIN_X_ENABLE, 1);
    gpio_set_level(PIN_Y_ENABLE, 1);
    gpio_set_level(PIN_Z_ENABLE, 1);
}

static bool any_driver_fault(void) {
    return fault_active(PIN_X_FAULT) || fault_active(PIN_Y_FAULT) || fault_active(PIN_Z_FAULT);
}

static void pwm_set_percent(ledc_channel_t channel, int percent) {
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    uint32_t duty = (uint32_t)((PWM_MAX * percent) / 100);
    ESP_ERROR_CHECK_WITHOUT_ABORT(ledc_set_duty(PWM_MODE, channel, duty));
    ESP_ERROR_CHECK_WITHOUT_ABORT(ledc_update_duty(PWM_MODE, channel));
}

static bool set_fan_percent(int percent) {
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    state_lock();
    // Match the tested 8-bit 0/128/255 duty mapping on IO21.
    uint32_t duty = (uint32_t)((FAN_PWM_MAX * percent + 50) / 100);
    esp_err_t err = ledc_set_duty_and_update(PWM_MODE, PWM_CH_FAN, duty, 0);
    if (err == ESP_OK) g_fan_percent = percent;
    state_unlock();
    ESP_ERROR_CHECK_WITHOUT_ABORT(err);
    return err == ESP_OK;
}

// GPIO17 camera illumination: fractional PWM duty and a 50% ceiling.
static void pwm_set_camera_light_percent(ledc_channel_t channel, float percent) {
    if (!isfinite(percent) || percent < 0.0f) percent = 0.0f;
    if (percent > CAMERA_LIGHT_MAX_PERCENT) percent = CAMERA_LIGHT_MAX_PERCENT;
    uint32_t duty = (uint32_t)lroundf((PWM_MAX * percent) / 100.0f);
    ESP_ERROR_CHECK_WITHOUT_ABORT(ledc_set_duty(PWM_MODE, channel, duty));
    ESP_ERROR_CHECK_WITHOUT_ABORT(ledc_update_duty(PWM_MODE, channel));
}

static void set_light_percent(float percent) {
    if (!isfinite(percent) || percent < 0.0f) percent = 0.0f;
    if (percent > CAMERA_LIGHT_MAX_PERCENT) percent = CAMERA_LIGHT_MAX_PERCENT;
    pwm_set_camera_light_percent(PWM_CH_LIGHT, percent);
    state_lock();
    g_light_percent = percent;
    state_unlock();
}

static void uv_off(void) {
    pwm_set_percent(PWM_CH_UV, 0);
    state_lock();
    g_uv_percent = 0;
    g_uv_active = false;
    g_uv_armed = false;
    g_uv_end_us = 0;
    state_unlock();
}

static void uv_set_percent(int percent) {
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    pwm_set_percent(PWM_CH_UV, percent);
    state_lock();
    g_uv_percent = percent;
    state_unlock();
}

static uint8_t sht_crc8(const uint8_t *data, int len) {
    uint8_t crc = 0xFF;
    for (int j = 0; j < len; ++j) {
        crc ^= data[j];
        for (int i = 0; i < 8; ++i) {
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
        }
    }
    return crc;
}

static bool read_tmp75(float *temp_c) {
    uint8_t reg = 0x00;
    uint8_t data[2] = {0};
    esp_err_t err = i2c_master_transmit_receive(g_tmp75, &reg, 1, data, 2, 100);
    if (err != ESP_OK) return false;

    // TMP75 temperature register is signed, left-justified. Dividing the
    // 16-bit signed value by 256 gives degrees C for the configured format.
    int16_t raw = (int16_t)(((uint16_t)data[0] << 8) | data[1]);
    *temp_c = (float)raw / 256.0f;
    return isfinite(*temp_c) && *temp_c > -60.0f && *temp_c < 150.0f;
}

static bool read_sht41(float *temp_c, float *rh) {
    uint8_t cmd = 0xFD; // high precision measurement
    uint8_t data[6] = {0};
    if (i2c_master_transmit(g_sht41, &cmd, 1, 100) != ESP_OK) return false;

    vTaskDelay(pdMS_TO_TICKS(12));
    if (i2c_master_receive(g_sht41, data, sizeof(data), 100) != ESP_OK) return false;
    if (sht_crc8(data, 2) != data[2] || sht_crc8(data + 3, 2) != data[5]) return false;

    uint16_t raw_t = ((uint16_t)data[0] << 8) | data[1];
    uint16_t raw_h = ((uint16_t)data[3] << 8) | data[4];
    *temp_c = -45.0f + 175.0f * ((float)raw_t / 65535.0f);
    *rh = -6.0f + 125.0f * ((float)raw_h / 65535.0f);
    if (*rh < 0.0f) *rh = 0.0f;
    if (*rh > 100.0f) *rh = 100.0f;
    return true;
}

static bool ina260_read_reg(uint8_t reg, uint16_t *value) {
    uint8_t data[2] = {0};
    if (i2c_master_transmit_receive(g_ina260, &reg, 1, data, 2, 100) != ESP_OK) return false;
    *value = ((uint16_t)data[0] << 8) | data[1];
    return true;
}

static bool read_ina260(float *voltage_v, float *current_ma, float *power_w) {
    uint16_t cur_raw = 0, volt_raw = 0, pwr_raw = 0;
    if (!ina260_read_reg(0x01, &cur_raw) ||
        !ina260_read_reg(0x02, &volt_raw) ||
        !ina260_read_reg(0x03, &pwr_raw)) {
        return false;
    }

    *current_ma = (float)((int16_t)cur_raw) * 1.25f;
    *voltage_v = (float)volt_raw * 0.00125f;
    *power_w = (float)pwr_raw * 0.010f;
    return true;
}

static void IRAM_ATTR fan_tach_isr(void *arg) {
    (void)arg;
    g_tach_pulses++;
}

static void sensor_task(void *arg) {
    (void)arg;
    uint32_t last_pulses = 0;
    int64_t last_rpm_us = esp_timer_get_time();

    while (1) {
        float pcb = NAN, amb = NAN, hum = NAN;
        float volts = NAN, current = NAN, power = NAN;

        bool tmp_ok = read_tmp75(&pcb);
        bool sht_ok = read_sht41(&amb, &hum);
        bool ina_ok = read_ina260(&volts, &current, &power);

        uint32_t pulses_now = g_tach_pulses;
        uint32_t delta = pulses_now - last_pulses;
        last_pulses = pulses_now;
        int64_t rpm_now_us = esp_timer_get_time();
        int64_t elapsed_us = rpm_now_us - last_rpm_us;
        last_rpm_us = rpm_now_us;
        uint32_t rpm = elapsed_us > 0 ?
            (uint32_t)((uint64_t)delta * 60000000ULL / (FAN_PULSES_PER_REV * elapsed_us)) : 0;

        state_lock();
        g_tmp75_ok = tmp_ok;
        g_sht41_ok = sht_ok;
        g_ina260_ok = ina_ok;
        g_pcb_temp_c = tmp_ok ? pcb : NAN;
        g_ambient_temp_c = sht_ok ? amb : NAN;
        g_humidity_rh = sht_ok ? hum : NAN;
        g_bus_voltage_v = ina_ok ? volts : NAN;
        g_bus_current_ma = ina_ok ? current : NAN;
        g_bus_power_w = ina_ok ? power : NAN;
        g_fan_rpm = rpm;
        bool auto_mode = g_fan_auto;
        state_unlock();

        if (auto_mode) {
            int target = 100; // fail-safe if TMP75 is absent/unreadable
            if (tmp_ok) {
                if (pcb < FAN_TEMP_1_C) target = 25;
                else if (pcb < FAN_TEMP_2_C) target = 45;
                else if (pcb < FAN_TEMP_3_C) target = 70;
                else target = 100;
            }
            state_lock();
            if (g_fan_auto) {
                uint32_t duty = (uint32_t)((FAN_PWM_MAX * target + 50) / 100);
                esp_err_t err = ledc_set_duty_and_update(PWM_MODE, PWM_CH_FAN, duty, 0);
                if (err == ESP_OK) g_fan_percent = target;
                ESP_ERROR_CHECK_WITHOUT_ABORT(err);
            }
            state_unlock();
        }

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

static void uv_task(void *arg) {
    (void)arg;
    while (1) {
        if (!g_link_expired &&
            (TickType_t)(xTaskGetTickCount() - g_last_host_tick) > pdMS_TO_TICKS(3000)) {
            g_link_expired = true;
            ++g_motion_epoch;
            xQueueReset(g_motor_queue);
            disable_all_motors();
            uv_off();
            state_lock();
            g_fan_auto = true;
            state_unlock();
            set_fan_percent(100);
            printf("EVENT LINK_TIMEOUT outputs_stopped\n");
        }
        bool active;
        int64_t end_us;
        state_lock();
        active = g_uv_active;
        end_us = g_uv_end_us;
        state_unlock();

        if (active && end_us > 0 && esp_timer_get_time() >= end_us) {
            uv_off();
            printf("EVENT UV_DONE\n");
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

static void motor_task(void *arg) {
    (void)arg;
    motor_cmd_t cmd;

    while (1) {
        if (xQueueReceive(g_motor_queue, &cmd, portMAX_DELAY) != pdTRUE) continue;
        if (cmd.epoch != g_motion_epoch) continue;

        int step_pin = step_pin_for_axis(cmd.axis);
        int dir_pin = dir_pin_for_axis(cmd.axis);
        int fault_pin = fault_pin_for_axis(cmd.axis);
        int32_t *position = position_for_axis(cmd.axis);
        if (step_pin < 0 || dir_pin < 0 || fault_pin < 0 || position == NULL) {
            printf("ERR MOVE invalid_axis\n");
            continue;
        }

        if (fault_active(fault_pin)) {
            set_axis_enabled(cmd.axis, false);
            printf("EVENT MOTOR_FAULT axis=%c\n", cmd.axis);
            continue;
        }

        uint32_t steps = (uint32_t)labs(cmd.pulses);
        int direction = cmd.pulses >= 0 ? 1 : 0;
        uint32_t pps = cmd.pps;
        if (pps < MIN_PPS) pps = MIN_PPS;
        if (pps > MAX_PPS) pps = MAX_PPS;
        uint32_t period_us = 1000000U / pps;
        if (period_us < (STEP_HIGH_US + 4U)) period_us = STEP_HIGH_US + 4U;

        state_lock();
        g_motor_busy = true;
        state_unlock();

        set_axis_enabled(cmd.axis, true);
        gpio_set_level(dir_pin, direction);
        esp_rom_delay_us(10);

        uint32_t completed = 0;
        for (uint32_t i = 0; i < steps; ++i) {
            if (cmd.epoch != g_motion_epoch || fault_active(fault_pin)) break;
            gpio_set_level(step_pin, 1);
            esp_rom_delay_us(STEP_HIGH_US);
            gpio_set_level(step_pin, 0);
            // Yield during long moves so USB and stop/watchdog tasks can run.
            uint32_t low_us = period_us - STEP_HIGH_US;
            if (low_us >= 1000) {
                vTaskDelay(pdMS_TO_TICKS(low_us / 1000));
                if (low_us % 1000) esp_rom_delay_us(low_us % 1000);
            } else {
                esp_rom_delay_us(low_us);
                if ((i & 15U) == 15U) vTaskDelay(1);
            }
            completed++;
        }

        state_lock();
        *position += direction ? (int32_t)completed : -(int32_t)completed;
        int32_t final_position = *position;
        g_motor_busy = false;
        state_unlock();

        if (fault_active(fault_pin)) {
            disable_all_motors();
            printf("EVENT MOTOR_FAULT axis=%c pos=%ld\n", cmd.axis, (long)final_position);
        } else if (cmd.epoch != g_motion_epoch) {
            disable_all_motors();
            printf("EVENT MOVE_STOPPED axis=%c pos=%ld\n", cmd.axis, (long)final_position);
        } else {
            printf("EVENT MOVE_DONE axis=%c pos=%ld\n", cmd.axis, (long)final_position);
        }
    }
}

static void print_status(void) {
    float pcb, amb, hum, volts, current, power;
    uint32_t rpm;
    int fan_pct, uv_pct;
    float light_pct;
    bool fan_auto, uv_active, moving, tmp_ok, sht_ok, ina_ok;
    int32_t xpos, ypos, zpos;

    state_lock();
    pcb = g_pcb_temp_c;
    amb = g_ambient_temp_c;
    hum = g_humidity_rh;
    volts = g_bus_voltage_v;
    current = g_bus_current_ma;
    power = g_bus_power_w;
    rpm = g_fan_rpm;
    fan_pct = g_fan_percent;
    fan_auto = g_fan_auto;
    light_pct = g_light_percent;
    uv_pct = g_uv_percent;
    uv_active = g_uv_active;
    moving = g_motor_busy;
    tmp_ok = g_tmp75_ok;
    sht_ok = g_sht41_ok;
    ina_ok = g_ina260_ok;
    xpos = g_pos_x;
    ypos = g_pos_y;
    zpos = g_pos_z;
    state_unlock();

    printf("STATUS uvmax=300 pcb=%.2f ambient=%.2f humidity=%.1f voltage=%.3f current=%.1f power=%.2f "
           "tmpok=%d shtok=%d inaok=%d fanrpm=%lu fanpct=%d fanauto=%d light=%.1f "
           "uv=%d uvactive=%d moving=%d xfault=%d yfault=%d zfault=%d "
           "xpos=%ld ypos=%ld zpos=%ld\n",
           pcb, amb, hum, volts, current, power,
           tmp_ok ? 1 : 0, sht_ok ? 1 : 0, ina_ok ? 1 : 0,
           (unsigned long)rpm, fan_pct, fan_auto ? 1 : 0, light_pct,
           uv_pct, uv_active ? 1 : 0, moving ? 1 : 0,
           fault_active(PIN_X_FAULT) ? 1 : 0,
           fault_active(PIN_Y_FAULT) ? 1 : 0,
           fault_active(PIN_Z_FAULT) ? 1 : 0,
           (long)xpos, (long)ypos, (long)zpos);
}

static void print_help(void) {
    printf("HELP PING VERSION STATUS HELP STOP MOVE ENABLE ZERO FAN LIGHT UV_ARM UV_CURE UV_STOP\n");
}

static bool valid_percent(int value) {
    return value >= 0 && value <= 100;
}

static void handle_command(char *line) {
    char *end = line + strlen(line);
    while (end > line && (end[-1] == '\r' || end[-1] == '\n' || end[-1] == ' ' || end[-1] == '\t')) {
        *--end = '\0';
    }
    while (*line == ' ' || *line == '\t') line++;
    if (*line == '\0') return;
    g_last_host_tick = xTaskGetTickCount();
    g_link_expired = false;

    if (strcmp(line, "PING") == 0) {
        printf("PONG\n");
        return;
    }
    if (strcmp(line, "VERSION") == 0) {
        printf("VERSION LOTUS_ESP32_S3 %s\n", FW_VERSION);
        return;
    }
    if (strcmp(line, "STATUS") == 0 || strcmp(line, "GET_STATUS") == 0) {
        print_status();
        return;
    }
    if (strcmp(line, "HELP") == 0) {
        print_help();
        return;
    }
    if (strcmp(line, "STOP") == 0) {
        ++g_motion_epoch;
        xQueueReset(g_motor_queue);
        disable_all_motors();
        uv_off();
        printf("OK STOP\n");
        return;
    }
    if (strcmp(line, "UV_STOP") == 0) {
        uv_off();
        printf("OK UV_STOP\n");
        return;
    }

    int enabled = 0;
    if (sscanf(line, "ENABLE ALL %d", &enabled) == 1) {
        if (enabled != 0 && enabled != 1) {
            printf("ERR ENABLE state_range\n");
            return;
        }
        if (enabled && any_driver_fault()) {
            printf("ERR ENABLE driver_fault\n");
            return;
        }
        if (!enabled) {
            ++g_motion_epoch;
            xQueueReset(g_motor_queue);
        }
        set_axis_enabled('X', enabled != 0);
        set_axis_enabled('Y', enabled != 0);
        set_axis_enabled('Z', enabled != 0);
        printf("OK ENABLE axis=ALL state=%d\n", enabled);
        return;
    }

    char axis = 0;
    if (sscanf(line, "ENABLE %c %d", &axis, &enabled) == 2) {
        if (axis >= 'a' && axis <= 'z') axis -= ('a' - 'A');
        if (axis != 'X' && axis != 'Y' && axis != 'Z') {
            printf("ERR ENABLE invalid_axis\n");
            return;
        }
        if (enabled != 0 && enabled != 1) {
            printf("ERR ENABLE state_range\n");
            return;
        }
        if (enabled && fault_active(fault_pin_for_axis(axis))) {
            printf("ERR ENABLE driver_fault axis=%c\n", axis);
            return;
        }
        if (!enabled) {
            ++g_motion_epoch;
            xQueueReset(g_motor_queue);
            disable_all_motors();
        }
        set_axis_enabled(axis, enabled != 0);
        printf("OK ENABLE axis=%c state=%d\n", axis, enabled);
        return;
    }

    long pulses = 0;
    unsigned long pps = 0;
    if (sscanf(line, "MOVE %c %ld %lu", &axis, &pulses, &pps) == 3) {
        if (axis >= 'a' && axis <= 'z') axis -= ('a' - 'A');
        if (axis != 'X' && axis != 'Y' && axis != 'Z') {
            printf("ERR MOVE invalid_axis\n");
            return;
        }
        if (pulses == 0 || pulses < -MAX_MOVE_PULSES || pulses > MAX_MOVE_PULSES) {
            printf("ERR MOVE pulse_range\n");
            return;
        }
        if (pps < MIN_PPS || pps > MAX_PPS) {
            printf("ERR MOVE pps_range\n");
            return;
        }
        if (fault_active(fault_pin_for_axis(axis))) {
            printf("ERR MOVE driver_fault axis=%c\n", axis);
            return;
        }

        motor_cmd_t cmd = {.axis = axis, .pulses = (int32_t)pulses,
                           .pps = (uint32_t)pps, .epoch = g_motion_epoch};
        if (xQueueSend(g_motor_queue, &cmd, pdMS_TO_TICKS(50)) == pdTRUE) {
            printf("OK MOVE axis=%c pulses=%ld pps=%lu\n", axis, pulses, pps);
        } else {
            printf("ERR MOVE queue_full\n");
        }
        return;
    }

    char zero_target[8] = {0};
    if (sscanf(line, "ZERO %7s", zero_target) == 1) {
        state_lock();
        bool busy = g_motor_busy;
        state_unlock();
        if (busy) {
            printf("ERR ZERO motor_busy\n");
            return;
        }

        state_lock();
        if (strcmp(zero_target, "ALL") == 0) {
            g_pos_x = g_pos_y = g_pos_z = 0;
        } else if (strcmp(zero_target, "X") == 0) {
            g_pos_x = 0;
        } else if (strcmp(zero_target, "Y") == 0) {
            g_pos_y = 0;
        } else if (strcmp(zero_target, "Z") == 0) {
            g_pos_z = 0;
        } else {
            state_unlock();
            printf("ERR ZERO invalid_axis\n");
            return;
        }
        state_unlock();
        printf("OK ZERO %s\n", zero_target);
        return;
    }

    int percent = 0;
    if (strcmp(line, "FAN AUTO") == 0) {
        state_lock();
        g_fan_auto = true;
        state_unlock();
        printf("OK FAN AUTO\n");
        return;
    }
    if (sscanf(line, "FAN %d", &percent) == 1) {
        if (!valid_percent(percent)) {
            printf("ERR FAN range\n");
            return;
        }
        state_lock();
        g_fan_auto = false;
        state_unlock();
        if (!set_fan_percent(percent)) {
            printf("ERR FAN pwm_update\n");
            return;
        }
        printf("OK FAN percent=%d\n", percent);
        return;
    }
    float light_percent = 0.0f;
    if (sscanf(line, "LIGHT %f", &light_percent) == 1) {
        if (!isfinite(light_percent) || light_percent < 0.0f || light_percent > CAMERA_LIGHT_MAX_PERCENT) {
            printf("ERR LIGHT range_max_50\n");
            return;
        }
        set_light_percent(light_percent);
        printf("OK LIGHT percent=%.1f\n", light_percent);
        return;
    }

    int arm = 0;
    if (sscanf(line, "UV_ARM %d", &arm) == 1) {
        if (arm != 0 && arm != 1) {
            printf("ERR UV_ARM state_range\n");
            return;
        }
        if (!arm) {
            uv_off();
        } else {
            state_lock();
            g_uv_armed = true;
            state_unlock();
        }
        printf("OK UV_ARM state=%d\n", arm);
        return;
    }

    int seconds = 0;
    if (sscanf(line, "UV_CURE %d %d", &seconds, &percent) == 2) {
        bool armed;
        state_lock();
        armed = g_uv_armed;
        state_unlock();

        if (!armed) {
            printf("ERR UV_CURE not_armed\n");
            return;
        }
        if (seconds < 1 || seconds > 300 || percent < 1 || percent > 100) {
            printf("ERR UV_CURE range\n");
            return;
        }

        uv_set_percent(percent);
        state_lock();
        g_uv_active = true;
        g_uv_end_us = esp_timer_get_time() + ((int64_t)seconds * 1000000LL);
        state_unlock();
        printf("OK UV_CURE seconds=%d percent=%d\n", seconds, percent);
        return;
    }

    printf("ERR unknown_command %s\n", line);
}

static void init_gpio(void) {
    // Preload active-low enable pins before switching them to outputs.
    gpio_set_level(PIN_X_ENABLE, 1);
    gpio_set_level(PIN_Y_ENABLE, 1);
    gpio_set_level(PIN_Z_ENABLE, 1);
    gpio_config_t outputs = {
        .pin_bit_mask = (1ULL << PIN_X_STEP) | (1ULL << PIN_X_DIR) |
                        (1ULL << PIN_Y_STEP) | (1ULL << PIN_Y_DIR) |
                        (1ULL << PIN_Z_STEP) | (1ULL << PIN_Z_DIR) |
                        (1ULL << PIN_X_ENABLE) | (1ULL << PIN_Y_ENABLE) |
                        (1ULL << PIN_Z_ENABLE),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&outputs));

    gpio_set_level(PIN_X_STEP, 0);
    gpio_set_level(PIN_Y_STEP, 0);
    gpio_set_level(PIN_Z_STEP, 0);
    gpio_set_level(PIN_X_DIR, 0);
    gpio_set_level(PIN_Y_DIR, 0);
    gpio_set_level(PIN_Z_DIR, 0);
    disable_all_motors();

    gpio_config_t faults = {
        .pin_bit_mask = (1ULL << PIN_X_FAULT) | (1ULL << PIN_Y_FAULT) | (1ULL << PIN_Z_FAULT),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&faults));

    gpio_config_t tach = {
        .pin_bit_mask = (1ULL << PIN_FAN_TACH),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&tach));

    esp_err_t isr_err = gpio_install_isr_service(0);
    if (isr_err != ESP_OK && isr_err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(isr_err);
    }
    ESP_ERROR_CHECK(gpio_isr_handler_add(PIN_FAN_TACH, fan_tach_isr, NULL));
}

static void init_pwm(void) {
    ledc_timer_config_t fan_timer = {
        .speed_mode = PWM_MODE,
        .duty_resolution = FAN_PWM_BITS,
        .timer_num = PWM_TIMER_FAN,
        .freq_hz = FAN_PWM_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&fan_timer));

    ledc_timer_config_t aux_timer = {
        .speed_mode = PWM_MODE,
        .duty_resolution = PWM_BITS,
        .timer_num = PWM_TIMER_AUX,
        .freq_hz = AUX_PWM_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&aux_timer));

    ledc_channel_config_t fan_ch = {
        .gpio_num = PIN_FAN_PWM,
        .speed_mode = PWM_MODE,
        .channel = PWM_CH_FAN,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = PWM_TIMER_FAN,
        .duty = 0,
        .hpoint = 0,
    };
    ledc_channel_config_t uv_ch = {
        .gpio_num = PIN_UV_DIM,
        .speed_mode = PWM_MODE,
        .channel = PWM_CH_UV,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = PWM_TIMER_AUX,
        .duty = 0,
        .hpoint = 0,
    };
    ledc_channel_config_t light_ch = {
        .gpio_num = PIN_LED_CTRL,
        .speed_mode = PWM_MODE,
        .channel = PWM_CH_LIGHT,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = PWM_TIMER_AUX,
        .duty = 0,
        .hpoint = 0,
    };

    ESP_ERROR_CHECK(ledc_channel_config(&fan_ch));
    // Keep LEDC output configuration as in the working IO21 fan test.
    // Tach input is IO40 with pull-up and falling-edge interrupt.
    ESP_ERROR_CHECK(ledc_channel_config(&uv_ch));
    ESP_ERROR_CHECK(ledc_channel_config(&light_ch));
    // Required by ledc_set_duty_and_update, even without a fade ramp.
    ESP_ERROR_CHECK(ledc_fade_func_install(0));

    // Safe startup: motors disabled, UV off, fan full until TMP75 is read.
    set_fan_percent(100);
    set_light_percent(12.5f);
    uv_off();
}

static void add_i2c_device(uint16_t address, i2c_master_dev_handle_t *handle) {
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = address,
        .scl_speed_hz = 100000,
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(g_i2c_bus, &dev_cfg, handle));
}

static void init_i2c(void) {
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = PIN_I2C_SDA,
        .scl_io_num = PIN_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = false,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &g_i2c_bus));
    add_i2c_device(ADDR_TMP75, &g_tmp75);
    add_i2c_device(ADDR_SHT41, &g_sht41);
    add_i2c_device(ADDR_INA260, &g_ina260);
}

void app_main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    esp_log_level_set("*", ESP_LOG_WARN);

    g_state_lock = xSemaphoreCreateMutex();
    g_motor_queue = xQueueCreate(8, sizeof(motor_cmd_t));
    if (g_state_lock == NULL || g_motor_queue == NULL) abort();

    init_gpio();
    init_pwm();
    init_i2c();
    g_last_host_tick = xTaskGetTickCount();

    xTaskCreate(motor_task, "lotus_motor", 4096, NULL, 8, NULL);
    xTaskCreate(sensor_task, "lotus_sensor", 4096, NULL, 5, NULL);
    xTaskCreate(uv_task, "lotus_uv", 3072, NULL, 6, NULL);

    printf("HELLO LOTUS_ESP32_S3 %s\n", FW_VERSION);
    printf("READY USB_SERIAL_JTAG\n");

    char line[256];
    size_t used = 0;

    while (1) {
        char chunk[64];
        int n = read(STDIN_FILENO, chunk, sizeof(chunk));
        if (n > 0) {
            for (int i = 0; i < n; ++i) {
                char c = chunk[i];
                if (c == '\n' || c == '\r') {
                    if (used > 0) {
                        line[used] = '\0';
                        handle_command(line);
                        used = 0;
                    }
                } else if (used < sizeof(line) - 1) {
                    line[used++] = c;
                } else {
                    used = 0;
                    printf("ERR line_too_long\n");
                }
            }
        } else {
            vTaskDelay(pdMS_TO_TICKS(10));
        }
    }
}
