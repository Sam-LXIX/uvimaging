LOTUS ESP32-S3 / 8 MB flash — 1.2.4-s3-8mb

This is a fresh ESP-IDF source project, not a precompiled binary.
Build on the Pi using an installed ESP-IDF 5.4.x or 5.5.x ESP32-S3 toolchain.
The package has not been compiled or tested on the physical PCB here.
It reuses the existing full LOTUS controller implementation; it is not
the old continuously running single-motor test.

INSTALL FROM GITHUB
1. Close LOTUS UI and any serial monitor.
2. Update the Pi checkout:
   git -C ~/uvimaging pull --ff-only
3. Hold BOOT, press/release RESET/EN, then release BOOT.
4. Build and flash:
   bash ~/uvimaging/firmware/LOTUS_ESP32S3_8MB/build_and_flash.sh
5. When flashing completes, press RESET/EN once without BOOT.
6. Open LOTUS UI and verify firmware 1.2.4-s3-8mb in Diagnostics.

INSTALL FROM ZIP
1. Save LOTUS_ESP32S3_8MB.zip to the Pi Downloads folder.
2. Close LOTUS UI and any serial monitor.
3. Extract with:
   unzip -o ~/Downloads/LOTUS_ESP32S3_8MB.zip -d ~/Lotus
4. Hold BOOT, press/release RESET/EN, then release BOOT.
5. Build and flash with:
   bash ~/Lotus/LOTUS_ESP32S3_8MB/build_and_flash.sh
6. When flashing completes, press RESET/EN once without holding BOOT.
7. Verify PONG and firmware version 1.2.4-s3-8mb in the UI Diagnostics.
   Do not start automatic alignment until controller communication and
   manual axis directions have been checked. Recalibrate motor response
   after changing the controller.

If ESP-IDF is installed elsewhere, source its export.sh before step 5.
If the port changed, pass it as an argument to build_and_flash.sh.
If connection fails, repeat BOOT + RESET and retry step 5.
The flash helper bypasses the missing system esptool stub file and uses
esptool from the active ESP-IDF Python environment. No erase-all is used.
It validates target, flash size, and file existence before sending a write.

CONTROLLER FEATURES
Native USB Serial/JTAG; LOTUS PING/STATUS and command protocol.
Left X and right Y/Z motor commands, fault monitoring, STOP and host timeout.
TMP75 PCB temperature, SHT41 humidity/temperature, INA260 voltage/current/power.
Fan automatic control and manual speed, with IO40 tachometer.
UV arm/disarm and timed curing up to 300 seconds. UV starts OFF and motors
start disabled. Starting the firmware alone does not command a motor move.
Voltage is input-bus voltage. Battery percentage is not invented; battery
chemistry and a confirmed battery-side sensing point are still needed.

PIN ASSIGNMENTS (same as existing full controller source)
X STEP/DIR/ENABLE/FAULT: 4 / 5 / 12 / 33
Y STEP/DIR/ENABLE/FAULT: 6 / 7 / 13 / 34
Z STEP/DIR/ENABLE/FAULT: 10 / 11 / 14 / 35
I2C SDA/SCL: 8 / 9
Illumination: 17; UV DIM: 18
Fan PWM: 21 (25 kHz); fan tach: 40
I2C addresses: INA260 0x40, SHT41 0x44, TMP75 0x48.
These assignments presume the replacement module is wired to the same
PCB signals as the previous controller.

FLASH CONFIGURATION
ESP32-S3, 8 MB, DIO, 40 MHz; native USB Serial/JTAG console; 1000 Hz RTOS.
PSRAM disabled because the module PSRAM type has not been identified.
The default app partition need not occupy all 8 MB of physical flash.
