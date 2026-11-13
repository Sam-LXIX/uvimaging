LOTUS ESP32-S3 / 8 MB flash — 1.2.5-s3-8mb

This is a fresh ESP-IDF source project, not a precompiled binary.
Build on the Pi using an installed ESP-IDF 5.4.x or 5.5.x ESP32-S3 toolchain.
This revision has host-side lighting regression tests, but still requires an
ESP-IDF build and testing on the physical PCB. The earlier 1.2.4 base was
successfully built/flashed on the user's Pi; that does not validate this revision.
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
6. Open LOTUS UI and verify firmware 1.2.5-s3-8mb in Diagnostics.

INSTALL FROM ZIP
1. Save LOTUS_ESP32S3_8MB.zip to the Pi Downloads folder.
2. Close LOTUS UI and any serial monitor.
3. Extract with:
   unzip -o ~/Downloads/LOTUS_ESP32S3_8MB.zip -d ~/Lotus
4. Hold BOOT, press/release RESET/EN, then release BOOT.
5. Build and flash with:
   bash ~/Lotus/LOTUS_ESP32S3_8MB/build_and_flash.sh
6. When flashing completes, press RESET/EN once without holding BOOT.
7. Verify PONG and firmware version 1.2.5-s3-8mb in the UI Diagnostics.
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
Camera illumination (GPIO17) starts at 12.5% and accepts 0–50%, including
fractional percentages. Invalid commands and PWM update failures return ERR.
UV (GPIO18) is independent: timed curing accepts 1–100%; UV_STOP turns it off.
Voltage is input-bus voltage. The UI's TalentCell percentage is a rough voltage
estimate; see BATTERY_ESTIMATE.md in the repository root for its limitations.

Updating Python alone does not update firmware startup brightness or its 50%
limit. Build/flash this revision and verify 1.2.5-s3-8mb in Diagnostics.

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
UNRESOLVED REV C MAPPING: the later supplied list calls 10/11/14 Motor X
and lists faults X35/Y36/Z37. It does not specify all Y/Z step/direction/enable
pins. This firmware retains the mapping above; reconcile it with the actual
board before motor operation. Do not infer that changing axis names alone fixes it.

FLASH CONFIGURATION
ESP32-S3, 8 MB, DIO, 40 MHz; native USB Serial/JTAG console; 1000 Hz RTOS.
PSRAM disabled because the module PSRAM type has not been identified.
The default app partition need not occupy all 8 MB of physical flash.

