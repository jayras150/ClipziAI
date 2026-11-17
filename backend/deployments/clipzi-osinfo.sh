#!/bin/sh
# Info OS host untuk tab System (dipanggil agent perintah host).
set -e
. /etc/os-release 2>/dev/null || true
KERNEL="$(uname -r 2>/dev/null || echo -)"
ARCH="$(uname -m 2>/dev/null || echo -)"
CORES="$(nproc 2>/dev/null || echo 0)"
MEM="$(awk '/MemTotal/ {printf "%d", $2*1024}' /proc/meminfo 2>/dev/null || echo 0)"
printf '{"name":"%s","version":"%s","id":"%s","kernel":"%s","arch":"%s","cores":%s,"memory_bytes":%s}\n' \
  "${PRETTY_NAME:-unknown}" "${VERSION_ID:-}" "${ID:-}" "$KERNEL" "$ARCH" "$CORES" "${MEM:-0}"
