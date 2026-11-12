#!/usr/bin/env bash
# ClipziAI - restore dari arsip hasil scripts/backup-all.sh
#
#   bash scripts/restore-all.sh /root/backup/clipzi-20260101-120000.tar.gz
#   bash scripts/restore-all.sh <arsip> --db-only
#   bash scripts/restore-all.sh <arsip> --config-only
set -euo pipefail

ARCHIVE="${1:-}"
shift || true
APP_DIR="${CLIPZI_APP_DIR:-/opt/clipzi/app}"
DB_ONLY=0
CONFIG_ONLY=0
PG_IMAGE="${CLIPZI_PG_IMAGE:-postgres:16-alpine}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db-only) DB_ONLY=1; shift ;;
    --config-only) CONFIG_ONLY=1; shift ;;
    --app-dir) APP_DIR="$2"; shift 2 ;;
    *) echo "Argumen tidak dikenal: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "Pemakaian: bash scripts/restore-all.sh <arsip.tar.gz> [--db-only|--config-only]" >&2
  exit 1
fi

WORK="$(mktemp -d /tmp/clipzi-restore-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

ARCHIVE="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"
echo "[1/6] Ekstrak $ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
( cd "$WORK" && sha256sum -c SHA256SUMS >/dev/null ) && echo "      checksum OK"

if [[ "$DB_ONLY" -eq 0 ]]; then
  echo "[2/6] Restore konfigurasi ke $APP_DIR"
  if [[ -d "$WORK/config" ]]; then
    ( cd "$WORK/config" && find . -type f -print0 | while IFS= read -r -d '' f; do
        dest="$APP_DIR/${f#./}"
        mkdir -p "$(dirname "$dest")"
        [[ -f "$dest" ]] && cp -a "$dest" "$dest.bak-$(date +%Y%m%d-%H%M%S)"
        cp -a "$f" "$dest"
      done )
  fi
  echo "      OK"

  echo "[3/6] Restore source code"
  if [[ -f "$WORK/repo.bundle" ]]; then
    if [[ -d "$APP_DIR/.git" ]]; then
      echo "      repo sudah ada -> bundle disimpan untuk inspeksi manual"
      cp -a "$WORK/repo.bundle" "$APP_DIR/backups/repo-$(date +%Y%m%d-%H%M%S).bundle" 2>/dev/null || true
    else
      git clone "$WORK/repo.bundle" "$APP_DIR"
    fi
  fi
fi

if [[ "$CONFIG_ONLY" -eq 0 && -f "$WORK/db/clipzi.dump" ]]; then
  echo "[4/6] Restore database"
  URL="$(grep -E '^DATABASE_URL=' "$APP_DIR/backend/.env" | head -1 | cut -d= -f2-)"
  URL="$(printf %s "$URL" | tr -d '"')"
  URL="${URL/postgresql+asyncpg:\/\//postgresql://}"
  docker run --rm -e PGCONNECT_TIMEOUT=20 -v "$WORK/db:/dump" "$PG_IMAGE"     pg_restore --clean --if-exists --no-owner --no-privileges -d "$URL" /dump/clipzi.dump
  echo "      OK"
fi

echo "[5/6] Nyalakan container"
( cd "$APP_DIR" && docker compose -f docker-compose.vps.yml up -d )

echo "[6/6] Cek kesehatan"
for i in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' https://proxyai.live/api/health || true)"
  if [[ "$code" == "200" ]]; then echo "      health 200 setelah ${i}x percobaan"; exit 0; fi
  sleep 5
done
echo "      PERINGATAN: /api/health belum 200 - cek 'docker logs clipzi-api'" >&2
exit 1
