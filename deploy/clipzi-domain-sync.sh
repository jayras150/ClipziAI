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
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
STATE_DIR="${STATE_DIR:-/var/lib/clipzi-domain-sync}"

mkdir -p "$STATE_DIR"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

[[ -f "$ENV_FILE" ]] || { log "ENV file tidak ada: $ENV_FILE"; exit 1; }

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

TOKEN="${CLIPZI_WORKER_TOKEN:-}"
[[ -n "$TOKEN" ]] || { log "CLIPZI_WORKER_TOKEN kosong."; exit 1; }

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
log "Backup .env -> $backup"

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

set_env DOMAIN "$DOMAIN"
[[ -n "$ADMIN_DOMAIN" ]] && set_env ADMIN_DOMAIN "$ADMIN_DOMAIN"

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
if ! docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d caddy >/dev/null 2>&1; then
  log "GAGAL compose caddy - .env dikembalikan."
  cp "$backup" "$ENV_FILE"
  RESULT_OK=false
  RESULT_ERR="docker compose up -d caddy gagal; .env dikembalikan"
else
  log "Caddy di-reload dengan domain baru."
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
