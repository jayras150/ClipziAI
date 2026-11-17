#!/bin/sh
# Uji kecepatan internet host (dipanggil agent perintah host).
# Memakai endpoint Cloudflare speed test; output JSON siap diparse backend.
set -e

DOWN_BYTES="${DOWN_BYTES:-25000000}"
UP_BYTES="${UP_BYTES:-10000000}"
TMP="$(mktemp /tmp/clipzi-speedtest.XXXXXX)"
trap 'rm -f "$TMP"' EXIT INT TERM

# Latency + unduh (bytes/sec dari curl)
LATENCY="$(curl -s -o /dev/null -w '%{time_starttransfer}' --max-time 10 \
  'https://speed.cloudflare.com/__down?bytes=1' 2>/dev/null || echo 0)"
DOWN_BPS="$(curl -s -o /dev/null -w '%{speed_download}' --max-time 30 \
  "https://speed.cloudflare.com/__down?bytes=${DOWN_BYTES}" 2>/dev/null || echo 0)"

# Unggah: buat berkas sementara lalu POST
dd if=/dev/zero of="$TMP" bs=1048576 count=$((UP_BYTES / 1048576)) 2>/dev/null || true
UP_BPS="$(curl -s -o /dev/null -w '%{speed_upload}' --max-time 30 \
  -X POST -H 'Content-Type: application/octet-stream' \
  --data-binary "@${TMP}" 'https://speed.cloudflare.com/__up' 2>/dev/null || echo 0)"

printf '{"down_bps":%s,"up_bps":%s,"latency_ms":%s,"down_bytes":%s,"up_bytes":%s}\n' \
  "${DOWN_BPS:-0}" "${UP_BPS:-0}" "$(awk -v v="${LATENCY:-0}" 'BEGIN{printf "%.1f", v*1000}')" \
  "${DOWN_BYTES}" "${UP_BYTES}"
