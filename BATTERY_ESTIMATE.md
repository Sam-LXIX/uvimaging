# TalentCell PB120B1 battery display

The footer and Diagnostics show a rough voltage-based percentage for the
user's PB120B1 (label: lithium-ion, 11.1 V, 12.8 Ah / 142.08 Wh, output 9–12.6 V).
Settings → Power source defaults to Battery alone for this installation.
Choose External / charging whenever a charger or external supply is connected.
The UI cannot detect that connection automatically.

This is not a calibrated state-of-charge measurement. The interpolation points
in BatteryEstimate.CURVE are a generic 3S lithium-ion heuristic, not a TalentCell
discharge curve. Load, wiring drop, temperature and aging affect the reading.
Values are rounded to 5% and explicitly labelled estimated. No runtime is
calculated from the PCB power reading, which may not include all device loads.

Only connected, valid INA260 telemetry less than three seconds old is accepted.
The gauge takes the median of distinct recent samples over ten seconds to
reduce brief load-induced jumps. Disconnection, invalid data, switching power
source, and telemetry gaps clear the history. Values at or below 20% show LOW.
This indication does not shut down, move motors, operate UV, or alter firmware.

No ESP32 reflash is needed. Pull main and restart LOTUS_UI_Cladding.py.
Headless regression check: python3 -m unittest discover -s checks -p test_battery_estimate.py
