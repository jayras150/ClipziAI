#!/bin/bash
# Backup penuh Clipzy: database (pg_dump) + env + compose ke /opt/clipzi/backups/<stamp>/
# Pemakaian: clipzi-backup.sh            -> buat backup baru, cetak JSON ringkasan
#            clipzi-backup.sh --list     -> daftar backup yang ada
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/clipzi/app}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/clipzi/backups}"
ENV_FILE="$APP_DIR/backend/.env"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_ROOT"

if [[ "${1:-}" == "--list" ]]; then
  find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d -printf '%f\n' 2>/dev/null | sort -r | head -20
  exit 0
fi

DEST="$BACKUP_ROOT/$STAMP"
if [[ -e "$DEST" ]]; then
  echo '{"ok":false,"error":"Folder backup untuk detik ini sudah ada"}'
  exit 1
fi
mkdir -p "$DEST"

db_url() {
  grep -E '^DATABASE_URL=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'"
}

DB_URL="$(db_url)"
DB_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"
DB_URL="${DB_URL/postgres+asyncpg:/postgres:}"
if [[ -z "$DB_URL" ]]; then
  echo '{"ok":false,"error":"DATABASE_URL tidak ditemukan di backend/.env"}'
  exit 1
fi

# Klien pg_dump lokal sering lebih lama dari server Supabase (mismatch versi).
# Pakai image postgres:17-alpine bila docker tersedia; fallback ke pg_dump lokal.
DUMP_CMD=()
if command -v docker >/dev/null 2>&1; then
  DUMP_CMD=(docker run --rm -i -e PGCONNECT_TIMEOUT=25 postgres:17-alpine pg_dump --no-owner --no-privileges)
else
  DUMP_CMD=(pg_dump --no-owner --no-privileges)
fi

set +e
"${DUMP_CMD[@]}" "$DB_URL" 2> "$DEST/pg_dump.err" | gzip -9 > "$DEST/db.sql.gz"
PG_STATUS=${PIPESTATUS[0]}
set -e

if [[ "$PG_STATUS" -ne 0 ]]; then
  DETAIL="$(tail -c 600 "$DEST/pg_dump.err" 2>/dev/null | tr '\n' ' ')"
  rm -f "$DEST/pg_dump.err" "$DEST/db.sql.gz"
  rmdir "$DEST" 2>/dev/null || true
  echo "{\"ok\":false,\"error\":\"pg_dump gagal\",\"detail\":\"${DETAIL//\"/'\"'}\"}"
  exit 1
fi
rm -f "$DEST/pg_dump.err"

[[ -f "$ENV_FILE" ]] && cp "$ENV_FILE" "$DEST/env.backup"
for f in "$APP_DIR"/docker-compose*.yml; do
  [[ -f "$f" ]] && cp "$f" "$DEST/" || true
done

python3 - "$DEST" "$STAMP" <<'PY'
import hashlib
import json
import os
import sys

dest, stamp = sys.argv[1], sys.argv[2]
files = []
for name in sorted(os.listdir(dest)):
    path = os.path.join(dest, name)
    if not os.path.isfile(path):
        continue
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    files.append({"name": name, "size": os.path.getsize(path), "sha256": digest.hexdigest()})

manifest = {
    "created_at": stamp,
    "host": os.uname().nodename,
    "app_dir": os.environ.get("APP_DIR", "/opt/clipzi/app"),
    "files": files,
    "notes": "Media/klip ada di object storage (R2) dan tidak disertakan di arsip ini.",
}
with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2)

print(json.dumps({"ok": True, "archive": stamp, "path": dest, "files": files}))
PY
