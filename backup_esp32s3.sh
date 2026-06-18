#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/cu.usbmodem42CEA4F10A401}"
FLASH_SIZE="${2:-0x800000}"
OUT_DIR="${3:-./backups}"

if [[ ! -x "./.venv-esptool/bin/esptool.py" ]]; then
  echo "Missing ./.venv-esptool/bin/esptool.py"
  echo "Run: python3 -m venv .venv-esptool && ./.venv-esptool/bin/pip install esptool"
  exit 1
fi

mkdir -p "${OUT_DIR}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="${OUT_DIR}/esp32s3-fullflash-${STAMP}.bin"

echo "Port: ${PORT}"
echo "Flash size: ${FLASH_SIZE}"
echo "Output: ${OUT_FILE}"

./.venv-esptool/bin/esptool.py \
  --chip esp32s3 \
  --port "${PORT}" \
  --baud 460800 \
  --before default_reset \
  --after no_reset \
  read_flash 0x0 "${FLASH_SIZE}" "${OUT_FILE}"

echo "Backup complete: ${OUT_FILE}"
