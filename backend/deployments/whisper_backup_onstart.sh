#!/bin/sh
# =============================================================================
# Warmup/backup cache Whisper di instance Vast (sekali jalan).
#
# Dipakai untuk membuat backup /workspace/whisper ke Google Drive:
#   onstart_cmd=/app/deployments/whisper_backup_onstart.sh
# Setelah model selesai diunduh, script menulis marker & tetap hidup 1 jam
# supaya admin/backend bisa menjalankan cloud_copy (Instance to Cloud).
# =============================================================================
set -eu

OUTPUT_DIR="${WHISPER_BACKUP_DIR:-/workspace/whisper_model}"
mkdir -p "$OUTPUT_DIR"
PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python"

echo "[whisper-backup] mengunduh model ke $OUTPUT_DIR"
"$PYTHON_BIN" - <<PY
from faster_whisper.utils import download_model

path = download_model("large-v3", output_dir="$OUTPUT_DIR")
print(f"[whisper-backup] selesai: {path}", flush=True)
PY

touch /workspace/whisper_ready
echo "WHISPER_READY"
sleep 3600
