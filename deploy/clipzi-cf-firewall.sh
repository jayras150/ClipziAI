#!/usr/bin/env bash
# ClipzyAI - firewall VPS: port 80/443 HANYA menerima trafik dari Cloudflare.
#
# Kenapa DOCKER-USER: Caddy berjalan di container dengan port yang di-publish
# Docker. Rule ufw pada INPUT tidak berlaku untuk trafik itu, jadi pembatasan
# harus di chain DOCKER-USER (iptables + ip6tables).
#
# SSH (22) TIDAK disentuh: chain ini hanya menangani tcp 80/443.
#
# Pemakaian:
#   /usr/local/sbin/clipzi-cf-firewall.sh            # terapkan (ambil IP CF terbaru)
#   /usr/local/sbin/clipzi-cf-firewall.sh --status   # lihat ringkasan rule
#
# Dijalankan otomatis saat boot oleh systemd unit clipzi-cf-firewall.service
# (After=docker.service) supaya rule dipasang setelah Docker membuat chain.
set -euo pipefail

if [[ "${1:-}" == "--status" ]]; then
  echo "== IPv4 DOCKER-USER =="
  iptables -S DOCKER-USER 2>/dev/null || true
  echo "== IPv6 DOCKER-USER =="
  ip6tables -S DOCKER-USER 2>/dev/null || true
  exit 0
fi

CF4="$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v4 || true)"
CF6="$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v6 || true)"

if [[ -z "$CF4" ]]; then
  echo "GAGAL mengambil daftar IP Cloudflare - aturan TIDAK diubah (mencegah lockout)." >&2
  exit 1
fi

# IPv4
iptables -F DOCKER-USER 2>/dev/null || true
iptables -A DOCKER-USER -i lo -j RETURN
iptables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
for net in $CF4; do
  iptables -A DOCKER-USER -p tcp -m multiport --dports 80,443 -s "$net" -j RETURN
done
iptables -A DOCKER-USER -p tcp -m multiport --dports 80,443 -j DROP

# IPv6 (kalau tersedia)
if command -v ip6tables >/dev/null 2>&1 && [[ -n "$CF6" ]]; then
  ip6tables -F DOCKER-USER 2>/dev/null || true
  ip6tables -A DOCKER-USER -i lo -j RETURN
  ip6tables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  for net in $CF6; do
    ip6tables -A DOCKER-USER -p tcp -m multiport --dports 80,443 -s "$net" -j RETURN
  done
  ip6tables -A DOCKER-USER -p tcp -m multiport --dports 80,443 -j DROP
fi

echo "OK: port 80/443 dibatasi ke Cloudflare ($(echo "$CF4" | wc -l) IPv4 + $(echo "$CF6" | wc -l) IPv6 range)"
