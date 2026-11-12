#!/usr/bin/env bash
set -euo pipefail
task_project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_project_dir"
if ! command -v idf.py >/dev/null 2>&1; then
    task_idf_export=""
    for task_candidate in "${IDF_PATH:-/nonexistent}/export.sh" "$HOME/esp/esp-idf/export.sh" "$HOME/esp/esp-idf-v5.5.1/export.sh"; do
        if [[ -f "$task_candidate" ]]; then task_idf_export="$task_candidate"; break; fi
    done
    if [[ -z "$task_idf_export" ]]; then
        echo 'ESP-IDF was not found. Nothing has been flashed.'
        echo 'Locate your installation: find ~/esp -maxdepth 5 -name export.sh 2>/dev/null'
        exit 1
    fi
    set +u
    source "$task_idf_export"
    set -u
fi
echo 'Building LOTUS 1.2.4-s3-8mb using ESP-IDF:'
idf.py --version
# This standalone project never builds in the old LOTUS firmware directory.
idf.py -DIDF_TARGET=esp32s3 build
python "$task_project_dir/flash_firmware.py" "${1:-/dev/ttyACM0}"
