# LOTUS fiber splicer

Raspberry Pi touchscreen UI and ESP32-S3 controller firmware.

Close the UI before updating. Update and launch on the Pi (one line):

`git -C ~/uvimaging pull --ff-only && /usr/bin/python3 ~/uvimaging/LOTUS_UI_Cladding.py`

The Verification page calculates optical insertion loss as
`10 * log10(pf1 / pf2)`, with both manually measured powers in mW.
Negative loss is retained as apparent gain so measurement problems are visible.
Measurements are saved in `~/.lotus_ui/verification.jsonl`.

Camera lighting defaults to 12.5%, with a 50% maximum. UV intensity is independent.
Python updates do not flash the controller: follow the
[firmware instructions](firmware/LOTUS_ESP32S3_8MB/README.txt) to install
firmware 1.2.5-s3-8mb and its fractional lighting control/ceiling.
That document also records the unresolved Rev C motor-pin mismatch.

- [Battery estimate limitations](BATTERY_ESTIMATE.md)
- [Cleave edge measurements](CLEAVE_MEASUREMENTS.md)
- [Recent review and validation](REVIEW_NOTES.md)

Run the headless tests with `python3 -m unittest discover -s checks -v`.
Tests need NumPy/Pillow; host firmware tests use GCC and do not touch hardware.
