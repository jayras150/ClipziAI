#!/bin/bash
# Restore Clipzy dari arsip backup: clipzi-restore.sh <stamp>
# Aman: hanya menerima nama folder di /opt/clipzi/backups (regex ketat).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/clipzi/app}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/clipzi/backups}"
ENV_FILE="$APP_DIR/backend/.env"
NAME="${1:-}"

if [[ ! "$NAME" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo '{"ok":false,"error":"Nama arsip tidak valid (format: 20260101T120000Z)"}'
  exit 1
fi

SRC="$BACKUP_ROOT/$NAME"
if [[ ! -d "$SRC" || ! -f "$SRC/db.sql.gz" ]]; then
  echo "{\"ok\":false,\"error\":\"Arsip $NAME tidak ditemukan atau db.sql.gz hilang\"}"
  exit 1
fi

DB_URL="$(grep -E '^DATABASE_URL=' "$SRC/env.backup" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
if [[ -z "$DB_URL" ]]; then
  DB_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
fi
DB_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"
DB_URL="${DB_URL/postgres+asyncpg:/postgres:}"
if [[ -z "$DB_URL" ]]; then
  echo '{"ok":false,"error":"DATABASE_URL tidak ditemukan (env.backup maupun backend/.env)"}'
  exit 1
fi

# Simpan env lama sebelum ditimpa.
if [[ -f "$ENV_FILE" ]]; then
  cp "$ENV_FILE" "$ENV_FILE.before-restore-$NAME" || true
fi

LOG="/tmp/clipzi-restore-$NAME.log"
PSQL_CMD=()
if command -v docker >/dev/null 2>&1; then
  PSQL_CMD=(docker run --rm -i -e PGCONNECT_TIMEOUT=25 postgres:17-alpine psql)
else
  PSQL_CMD=(psql)
fi

set +e
gunzip -c "$SRC/db.sql.gz" | "${PSQL_CMD[@]}" "$DB_URL" -v ON_ERROR_STOP=0 > "$LOG" 2>&1
PSQL_STATUS=${PIPESTATUS[1]}
set -e

ENV_RESTORED=false
if [[ -f "$SRC/env.backup" ]]; then
  cp "$SRC/env.backup" "$ENV_FILE"
  ENV_RESTORED=true
fi

for f in "$SRC"/docker-compose*.yml; do
  [[ -f "$f" ]] && cp "$f" "$APP_DIR/$(basename "$f")" || true
done

ERRORS="$(grep -ci 'error:' "$LOG" 2>/dev/null || echo 0)"
DETAIL="$(tail -c 400 "$LOG" 2>/dev/null | tr '\n' ' ')"

if [[ "$PSQL_STATUS" -ne 0 && "$ERRORS" -gt 0 ]]; then
  echo "{\"ok\":false,\"archive\":\"$NAME\",\"error\":\"Restore DB selesai dengan error (lihat log)\",\"psql_status\":$PSQL_STATUS,\"errors\":$ERRORS,\"detail\":\"${DETAIL//\"/'\"'}\",\"log\":\"$LOG\"}"
  exit 1
fi

echo "{\"ok\":true,\"archive\":\"$NAME\",\"env_restored\":$ENV_RESTORED,\"warnings\":$ERRORS,\"log\":\"$LOG\",\"detail\":\"${DETAIL//\"/'\"'}\"}"
