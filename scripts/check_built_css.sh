#!/usr/bin/env bash
# Verifikasi cepat: selector penting benar-benar ada di CSS hasil build.
set -u
rm -rf /tmp/csscheck
docker cp clipzi-web:/app/.next/static/css /tmp/csscheck >/dev/null
for s in ui-card ui-btn-gold ui-input clip-card ui-table ui-stat style-card clip-modal ui-admin-split wm-logo-row ui-progress ui-tabs clip-hook viral-bubble; do
  n=$(grep -o "\.$s" /tmp/csscheck/*.css | wc -l)
  echo "$s: $n"
done
echo "--- total bytes css ---"
du -sb /tmp/csscheck | cut -f1
