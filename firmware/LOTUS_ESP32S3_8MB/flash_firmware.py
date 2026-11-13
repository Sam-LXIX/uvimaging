"""Flash the just-built 8 MB controller using ROM mode, without a stub file."""
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
build = root / 'build'
args = json.loads((build / 'flasher_args.json').read_text())
if args['extra_esptool_args']['chip'] != 'esp32s3':
    raise SystemExit('Wrong target: nothing flashed.')
if args['flash_settings']['flash_size'] != '8MB':
    raise SystemExit('Build is not configured for 8 MB: nothing flashed.')
files = args['flash_files']
if not files or any(not (build / filename).is_file() for filename in files.values()):
    raise SystemExit('Missing firmware binaries: nothing flashed.')
version = int(importlib.metadata.version('esptool').split('.')[0])
modern = version >= 5
command = [sys.executable, '-m', 'esptool', '--chip', 'esp32s3',
           '--port', sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0',
           '--baud', '115200', '--no-stub', '--before',
           'no-reset' if modern else 'no_reset', '--after',
           'no-reset' if modern else 'no_reset',
           'write-flash' if modern else 'write_flash']
for flag, value in [('flash_mode', args['flash_settings']['flash_mode']),
                    ('flash_freq', args['flash_settings']['flash_freq']),
                    ('flash_size', '8MB')]:
    command.extend(['--' + (flag.replace('_', '-') if modern else flag), value])
for address, filename in sorted(files.items(), key=lambda item: int(item[0], 16)):
    command.extend([address, str(build / filename)])
print('Keep LOTUS UI closed. Flashing via ROM bootloader; no erase-all command.', flush=True)
subprocess.run(command, check=True)
print('Flash command completed. Release BOOT, then press RESET/EN once to start LOTUS.')
print('Expected firmware version: 1.2.5-s3-8mb. Verify PONG and STATUS before motor/UV use.')

