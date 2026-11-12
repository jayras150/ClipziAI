#!/usr/bin/env bash
# ClipziAI - backup SEMUA komponen ke SATU file arsip.
#
# Isi arsip:
#   db/clipzi.dump      -> pg_dump -Fc (data + skema)
#   db/schema.sql       -> skema saja (referensi cepat)
#   repo.bundle         -> git bundle --all (seluruh source backend+frontend, semua branch)
#   config/             -> .env, docker-compose, Caddyfile, deployments, TODO (file yang TIDAK ada di git)
#   images.txt          -> image + digest yang sedang dipakai
#   manifest.txt        -> ringkasan + daftar file
#   SHA256SUMS          -> checksum untuk verifikasi saat restore
#
# Contoh:
#   bash scripts/backup-all.sh
#   bash scripts/backup-all.sh --skip-db
#   bash scripts/backup-all.sh --out /root/backup-clipzi
set -euo pipefail

APP_DIR="${CLIPZI_APP_DIR:-/opt/clipzi/app}"
OUT_DIR=""
SKIP_DB=0
DB_ONLY=0
PG_IMAGE="${CLIPZI_PG_IMAGE:-postgres:16-alpine}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-db) SKIP_DB=1; shift ;;
    --db-only) DB_ONLY=1; shift ;;
    --out) OUT_DIR="$2"; shift 2 ;;
    --app-dir) APP_DIR="$2"; shift 2 ;;
    -h|--help) sed -n "2,20p" "$0"; exit 0 ;;
    *) echo "Argumen tidak dikenal: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -d "$APP_DIR" ]]; then
  echo "Folder aplikasi tidak ditemukan: $APP_DIR" >&2
  exit 1
fi
OUT_DIR="${OUT_DIR:-$APP_DIR/backups}"
mkdir -p "$OUT_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="$(mktemp -d /tmp/clipzi-backup-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/db" "$WORK/config"

if [[ "$DB_ONLY" -eq 1 ]]; then SKIP_DB=0; fi

# --- 1) Database -------------------------------------------------------------
if [[ "$SKIP_DB" -eq 0 ]]; then
  if [[ "$DB_ONLY" -eq 1 ]]; then
    URL="${DATABASE_URL:-}"
    if [[ -z "$URL" && -f "$APP_DIR/backend/.env" ]]; then
      URL="$(grep -E '^DATABASE_URL=' "$APP_DIR/backend/.env" | head -1 | cut -d= -f2-)"
    fi
  else
    URL="$(grep -E '^DATABASE_URL=' "$APP_DIR/backend/.env" | head -1 | cut -d= -f2- || true)"
  fi
  URL="${URL//\"/}"
  URL="${URL/postgresql+asyncpg:\/\//postgresql://}"
  if [[ -z "$URL" ]]; then
    echo "DATABASE_URL tidak ditemukan - dump database dilewati" >&2
  else
    echo "[1/5] Dump database..."
    docker run --rm -e PGCONNECT_TIMEOUT=20 -v "$WORK/db:/dump" "$PG_IMAGE"       pg_dump --no-owner --no-privileges -Fc -d "$URL" -f /dump/clipzi.dump
    docker run --rm -e PGCONNECT_TIMEOUT=20 -v "$WORK/db:/dump" "$PG_IMAGE"       pg_dump --no-owner --no-privileges --schema-only -d "$URL" -f /dump/schema.sql || true
    echo "      OK: $(du -h "$WORK/db/clipzi.dump" | cut -f1)"
  fi
else
  echo "[1/5] Dump database dilewati (--skip-db)"
fi

# --- 2) Source code (semua branch + commit) ----------------------------------
if [[ "$DB_ONLY" -eq 0 ]]; then
  echo "[2/5] Bundle git..."
  git -C "$APP_DIR" bundle create "$WORK/repo.bundle" --all >/dev/null
  echo "      OK: $(du -h "$WORK/repo.bundle" | cut -f1)"
else
  echo "[2/5] Bundle git dilewati (--db-only)"
fi

# --- 3) Konfigurasi & file yang tidak ada di git -----------------------------
if [[ "$DB_ONLY" -eq 0 ]]; then
  echo "[3/5] Salin konfigurasi..."
  for item in backend/.env .env .env.local docker-compose.vps.yml docker-compose.yml docker-compose.prod.yml Caddyfile Caddyfile.prod TODO.md TODO.html; do
    if [[ -e "$APP_DIR/$item" ]]; then
      mkdir -p "$WORK/config/$(dirname "$item")"
      cp -a "$APP_DIR/$item" "$WORK/config/$item"
    fi
  done
  for pattern in "backend/.env*" "frontend/.env*" "Caddyfile*"; do
    for f in $APP_DIR/$pattern; do
      [[ -e "$f" ]] || continue
      rel="${f#$APP_DIR/}"
      mkdir -p "$WORK/config/$(dirname "$rel")"
      cp -a "$f" "$WORK/config/$rel"
    done
  done
  chmod -R go-rwx "$WORK/config"
  echo "      OK: $(find "$WORK/config" -type f | wc -l) file"
fi

# --- 4) Image & manifest -----------------------------------------------------
if [[ "$DB_ONLY" -eq 0 ]]; then
  echo "[4/5] Catat image..."
  docker images --digests --format '{{.Repository}}:{{.Tag}} {{.Digest}}'     | grep -E 'clipzi|caddy' > "$WORK/images.txt" || true
  {
    echo "ClipziAI backup"
    echo "waktu       : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host        : $(hostname)"
    echo "app_dir     : $APP_DIR"
    echo "commit      : $(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || echo '-')"
    echo "branch      : $(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '-')"
    echo "db_dump     : $(du -h "$WORK/db/clipzi.dump" 2>/dev/null | cut -f1 || echo '-')"
    echo
    echo "--- file ---"
    find "$WORK" -type f -printf '%P
' | sort
  } > "$WORK/manifest.txt"
fi

# --- 5) Arsip ----------------------------------------------------------------
ARCHIVE="$OUT_DIR/clipzi-$STAMP.tar.gz"
echo "[5/5] Membuat arsip..."
( cd "$WORK" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
tar -czf "$ARCHIVE" -C "$WORK" .
chmod 600 "$ARCHIVE"
echo
echo "SELESAI: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
echo "Verifikasi: tar -tzf $ARCHIVE | head"
echo "Restore   : bash scripts/restore-all.sh $ARCHIVE"
