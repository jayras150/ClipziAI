#!/usr/bin/env bash
# =============================================================================
# ClipzyAI - agent penerap ganti domain (dijalankan di VPS)
#
# Backend berjalan di container dan TIDAK punya akses ke host, jadi tidak bisa
# menulis .env atau reload Caddy. Alur "ganti domain 1 klik":
#
#   dashboard admin  ->  POST /api/admin/settings/platform/apply-domain
#                    ->  platform_settings: domain_status = pending
#   agent (timer 30s) -> GET  /api/internal/domain-task        (butuh token)
#                    ->  backup .env, tulis DOMAIN & ADMIN_DOMAIN
#                    ->  docker compose up -d caddy
#                    ->  opsional: update DNS Cloudflare (A, proxied)
#                    -> POST /api/internal/domain-applied       (status applied)
#
# Pasang sebagai systemd timer: clipzi-domain-sync.timer (tiap 30 detik).
#
# ENV yang dibaca dari /opt/clipzi/app/.env:
#   CLIPZI_WORKER_TOKEN   -> token ke backend (wajib)
#   CLOUDFLARE_API_TOKEN  -> opsional, update DNS otomatis
#   CLOUDFLARE_ZONE_ID    -> opsional
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/clipzi/app}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.vps.yml}"
# Token & FRONTEND_URL ada di backend/.env; domain publik dibaca Caddy dari
# compose (environment: DOMAIN/ADMIN_DOMAIN) dan frontend dari NEXT_PUBLIC_API_URL.
ENV_FILE="${ENV_FILE:-$APP_DIR/backend/.env}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
STATE_DIR="${STATE_DIR:-/var/lib/clipzi-domain-sync}"

mkdir -p "$STATE_DIR"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

[[ -f "$ENV_FILE" ]] || { log "ENV file tidak ada: $ENV_FILE"; exit 1; }

# JANGAN `source` file .env: beberapa nilai berisi spasi/kutip sehingga bisa
# dieksekusi sebagai perintah. Ambil hanya key yang dibutuhkan.
get_env() {
  { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"; } || true
}

TOKEN="$(get_env CLIPZI_WORKER_TOKEN)"
CLOUDFLARE_API_TOKEN="$(get_env CLOUDFLARE_API_TOKEN)"
CLOUDFLARE_ZONE_ID="$(get_env CLOUDFLARE_ZONE_ID)"
[[ -n "$TOKEN" ]] || { log "CLIPZI_WORKER_TOKEN kosong di $ENV_FILE."; exit 1; }

TASK_JSON="$(curl -fsS --max-time 20 -H "X-Clipzi-Token: $TOKEN" "$BACKEND_URL/api/internal/domain-task" || true)"
[[ -n "$TASK_JSON" ]] || { log "Backend tidak merespons domain-task (lewati)."; exit 0; }

PENDING="$(printf '%s' "$TASK_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("pending"))' 2>/dev/null || echo False)"
[[ "$PENDING" == "True" ]] || exit 0

DOMAIN="$(printf '%s' "$TASK_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("domain") or "")')"
ADMIN_DOMAIN="$(printf '%s' "$TASK_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("admin_domain") or "")')"
[[ -n "$DOMAIN" ]] || { log "Pending tanpa domain - dilewati."; exit 0; }

# Cegah dua instance agent berjalan bersamaan.
exec 9>"$STATE_DIR/lock"
flock -n 9 || { log "Agent lain sedang berjalan - keluar."; exit 0; }

log "Menerapkan domain: $DOMAIN (admin: ${ADMIN_DOMAIN:-'-'})"

backup="$STATE_DIR/env.$(date -u +%Y%m%d-%H%M%S).bak"
cp "$ENV_FILE" "$backup"
COMPOSE_BACKUP="$STATE_DIR/compose.$(date -u +%Y%m%d-%H%M%S).bak"
cp "$COMPOSE_FILE" "$COMPOSE_BACKUP"
log "Backup .env -> $backup, compose -> $COMPOSE_BACKUP"

set_env() {
  python3 - "$ENV_FILE" "$1" "$2" <<'PY'
import io, sys
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
lines = io.open(path, encoding='utf-8').read().splitlines()
found = False
out = []
for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}={value}")
        found = True
    else:
        out.append(line)
if not found:
    out.append(f"{key}={value}")
io.open(path, 'w', encoding='utf-8', newline='\n').write("\n".join(out) + "\n")
PY
}

set_env FRONTEND_URL "https://$DOMAIN"

# Tulis domain ke compose (Caddy membaca DOMAIN/ADMIN_DOMAIN, frontend membaca
# NEXT_PUBLIC_API_URL). Nilainya berupa URL lengkap https://<domain>.
python3 - "$COMPOSE_FILE" "$DOMAIN" "$ADMIN_DOMAIN" <<'PY'
import io, re, sys
path, domain, admin = sys.argv[1], sys.argv[2], sys.argv[3]
text = io.open(path, encoding='utf-8').read()

def set_key(text, key, value):
    pattern = re.compile(rf"(?m)^(\s*){key}:\s*.*$")
    if pattern.search(text):
        return pattern.sub(lambda m: f"{m.group(1)}{key}: {value}", text, count=1)
    return text

text = set_key(text, "DOMAIN", f"https://{domain}")
text = set_key(text, "NEXT_PUBLIC_API_URL", f"https://{domain}")
if admin:
    text = set_key(text, "ADMIN_DOMAIN", f"https://{admin}")
io.open(path, 'w', encoding='utf-8', newline='\n').write(text)
PY
log "Compose diperbarui (DOMAIN/NEXT_PUBLIC_API_URL${ADMIN_DOMAIN:+/ADMIN_DOMAIN})."

DNS_RESULT="skipped"
if [[ -n "${CLOUDFLARE_API_TOKEN:-}" && -n "${CLOUDFLARE_ZONE_ID:-}" ]]; then
  IP="$(curl -fsS --max-time 10 https://api.ipify.org || true)"
  if [[ -n "$IP" ]]; then
    for name in "$DOMAIN" ${ADMIN_DOMAIN:+"$ADMIN_DOMAIN"}; do
      rec_id="$(curl -fsS --max-time 20 \
        -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
        "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records?type=A&name=$name" \
        | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d.get("result") or []; print(r[0]["id"] if r else "")' 2>/dev/null || true)"
      payload="{\"type\":\"A\",\"name\":\"$name\",\"content\":\"$IP\",\"proxied\":true,\"ttl\":1}"
      if [[ -n "$rec_id" ]]; then
        curl -fsS --max-time 20 -X PUT \
          -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
          -H 'Content-Type: application/json' --data "$payload" \
          "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records/$rec_id" >/dev/null \
          && log "DNS $name -> $IP (update)" || log "Gagal update DNS $name"
      else
        curl -fsS --max-time 20 -X POST \
          -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
          -H 'Content-Type: application/json' --data "$payload" \
          "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records" >/dev/null \
          && log "DNS $name -> $IP (dibuat)" || log "Gagal membuat DNS $name"
      fi
    done
    DNS_RESULT="ok"
  else
    DNS_RESULT="ip-unknown"
    log "IP publik tidak terdeteksi; DNS dilewati."
  fi
fi

RESULT_OK=true
RESULT_ERR=""
if ! docker compose -f "$COMPOSE_FILE" up -d caddy frontend >/dev/null 2>&1; then
  log "GAGAL compose caddy/frontend - .env & compose dikembalikan."
  cp "$backup" "$ENV_FILE"
  cp "$COMPOSE_BACKUP" "$COMPOSE_FILE"
  docker compose -f "$COMPOSE_FILE" up -d caddy frontend >/dev/null 2>&1 || true
  RESULT_OK=false
  RESULT_ERR="docker compose up -d caddy frontend gagal; konfigurasi dikembalikan"
else
  log "Caddy & frontend di-reload dengan domain baru."
fi

if [[ -n "$ADMIN_DOMAIN" ]]; then
  ADMIN_JSON="\"$ADMIN_DOMAIN\""
else
  ADMIN_JSON="null"
fi

curl -fsS --max-time 20 -X POST \
  -H "X-Clipzi-Token: $TOKEN" \
  -H 'Content-Type: application/json' \
  --data "{\"domain\":\"$DOMAIN\",\"admin_domain\":$ADMIN_JSON,\"ok\":$RESULT_OK,\"error\":\"$RESULT_ERR\"}" \
  "$BACKEND_URL/api/internal/domain-applied" >/dev/null \
  && log "Laporan terkirim (ok=$RESULT_OK, dns=$DNS_RESULT)" \
  || log "Gagal mengirim laporan ke backend."

log "Selesai."
