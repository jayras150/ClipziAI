#!/bin/bash
# Build + jalankan admin panel (TailAdmin) di VPS.
#
# Pemakaian (setelah folder admin/ ada di Batch D):
#   bash /tmp/build_admin.sh
#
# Catatan: build dilakukan di VPS (bukan GitHub Actions) supaya workflow backend
# yang sudah stabil tidak ikut berubah.
exec > /tmp/admin_build.log 2>&1
set -x
date -u
cd /opt/clipzi/app || exit 1

COMPOSE="docker compose -f docker-compose.vps.yml -f docker-compose.admin.yml"

# Pastikan dependency terpasang (npm ci butuh package-lock.json).
if [ ! -f admin/package-lock.json ]; then
    echo "PERINGATAN: admin/package-lock.json tidak ada; jalankan npm install dulu."
fi

$COMPOSE build admin
echo "BUILD_RC=$?"

$COMPOSE up -d admin
echo "UP_RC=$?"

docker image prune -f
date -u
echo ADMIN_BUILD_DONE
