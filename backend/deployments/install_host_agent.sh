#!/usr/bin/env bash
# Pasang / perbarui agent perintah host ClipzyAI (idempotent).
#
#   bash backend/deployments/install_host_agent.sh
#
# Agent metrik (`clipzi-host-metrics`) sudah ada sejak awal; script ini hanya
# menambahkan agent perintah (clear cache, restart Caddy, prune Docker).
set -euo pipefail

SCRIPT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/clipzi-host-commands.py"
SCRIPT_DST="/usr/local/sbin/clipzi-host-commands.py"
UNIT="/etc/systemd/system/clipzi-host-commands.service"

if [[ ! -f "$SCRIPT_SRC" ]]; then
  echo "Tidak menemukan $SCRIPT_SRC" >&2
  exit 1
fi

install -m 0755 "$SCRIPT_SRC" "$SCRIPT_DST"

BASE_DIR="$(dirname "$SCRIPT_SRC")"
for extra in clipzi-osinfo.sh clipzi-speedtest.sh clipzi-backup.sh clipzi-restore.sh; do
  if [[ -f "$BASE_DIR/$extra" ]]; then
    install -m 0755 "$BASE_DIR/$extra" "/usr/local/sbin/$extra"
    echo "terpasang: /usr/local/sbin/$extra"
  fi
done

cat > "$UNIT" <<'UNIT_EOF'
[Unit]
Description=ClipzyAI host command agent (clear cache / restart Caddy / prune Docker)
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/sbin/clipzi-host-commands.py
Environment=INTERVAL=3
Restart=always
RestartSec=5
Nice=5

[Install]
WantedBy=multi-user.target
UNIT_EOF

systemctl daemon-reload
systemctl enable clipzi-host-commands.service >/dev/null 2>&1 || true
systemctl restart clipzi-host-commands.service
sleep 2
systemctl --no-pager --lines=5 status clipzi-host-commands.service || true
echo "OK: agent perintah host terpasang di $SCRIPT_DST"
