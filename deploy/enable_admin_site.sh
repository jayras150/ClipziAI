#!/bin/bash
# Mengaktifkan site admin di Caddyfile setelah DNS + IP allowlist siap.
#
# Prasyarat:
#   - DNS A record: admin.proxyai.live -> IP VPS
#   - backend/.env atau environment compose berisi:
#       ADMIN_DOMAIN=admin.proxyai.live
#       ADMIN_ALLOWED_IPS=1.2.3.4            (boleh lebih dari satu, pisah koma)
#   - container `admin` sudah jalan (Batch D)
#
# Script ini idempoten: kalau blok sudah aktif, tidak melakukan apa-apa.
set -eu
exec > /tmp/enable_admin_site.log 2>&1
set -x

cd /opt/clipzi/app || exit 1

if [ -z "${ADMIN_DOMAIN:-}" ] || [ -z "${ADMIN_ALLOWED_IPS:-}" ]; then
    echo "ADMIN_DOMAIN / ADMIN_ALLOWED_IPS belum di-set di environment."
    echo "Contoh:"
    echo "  export ADMIN_DOMAIN=admin.proxyai.live"
    echo "  export ADMIN_ALLOWED_IPS=103.xx.xx.xx"
    exit 1
fi

# Ambil IP allowlist dari environment, lalu uncomment blok site admin.
python3 - <<'PY'
import os
import re
from pathlib import Path

path = Path("deploy/Caddyfile")
text = path.read_text(encoding="utf-8")
domain = os.environ["ADMIN_DOMAIN"].strip()
allowed = os.environ["ADMIN_ALLOWED_IPS"].strip()

if domain in text and "handle @allowed" in text.split(domain, 1)[1][:400]:
    print("Site admin sudah aktif.")
    raise SystemExit(0)

lines = text.splitlines()
out, in_block, changed = [], False, False
for line in lines:
    stripped = line.strip()
    if stripped.startswith("# {$ADMIN_DOMAIN}"):
        in_block = True
        out.append(line.replace("# {$ADMIN_DOMAIN}", domain).replace("# ", "", 1))
        changed = True
        continue
    if in_block:
        if stripped.startswith("# }") and line.startswith("# }") and line.rstrip() == "# }":
            out.append("}")
            in_block = False
            continue
        # buang komentar di awal baris (tanpa merusak isi seperti "#ffffff")
        out.append(re.sub(r"^#\s?", "", line) if line.lstrip().startswith("#") else line)
        continue
    out.append(line)

if not changed:
    print("Blok site admin tidak ditemukan di Caddyfile.")
    raise SystemExit(1)

text = "\n".join(out).replace("{$ADMIN_ALLOWED_IPS}", allowed)
path.write_text(text + "\n", encoding="utf-8")
print("Site admin diaktifkan untuk domain", domain)
PY

docker compose -f docker-compose.vps.yml -f docker-compose.admin.yml \
    up -d --force-recreate caddy admin
echo ENABLE_ADMIN_SITE_DONE
