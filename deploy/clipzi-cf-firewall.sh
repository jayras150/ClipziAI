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

if [[ "${1:-}" == "--check" ]]; then
  # Uji outbound HTTPS dari dalam container: kalau DROP salah arah (tanpa -i WAN)
  # hasilnya 000 / timeout dan semua panggilan AI & Vast akan gagal.
  echo "== uji outbound container =="
  for target in https://example.com https://openrouter.ai/api/v1/models; do
    code="$(docker exec clipzi-api timeout 15 /usr/bin/curl -s -o /dev/null -w '%{http_code}' "$target" 2>/dev/null || true)"
    echo "  $target -> ${code:-000}"
  done
  echo "== counter DROP =="
  iptables -L DOCKER-USER -v -n 2>/dev/null | tail -2 || true
  exit 0
fi

CF4="$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v4 || true)"
CF6="$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v6 || true)"

if [[ -z "$CF4" ]]; then
  echo "GAGAL mengambil daftar IP Cloudflare - aturan TIDAK diubah (mencegah lockout)." >&2
  exit 1
fi

# PENTING: chain DOCKER-USER juga dilewati trafik KELUAR (outbound) dari
# container, karena paketnya melewati FORWARD. Tanpa batasan interface,
# rule DROP di bawah akan memblokir SEMUA outbound HTTP/HTTPS container
# (gejala: AI test timeout/HTTP 000, console.vast.ai hang, startup API 502,
# upload log bundle gagal).
#
# Karena itu semua rule memakai `-i "$WAN"` sehingga hanya menyentuh trafik
# yang MASUK dari internet lewat NIC publik. Trafik antar-container dan
# outbound container (masuk lewat docker0/br-*) tidak tersentuh.
WAN="$(ip route show default | awk '{print $5; exit}')"
if [[ -z "${WAN:-}" ]]; then
  echo "GAGAL menentukan interface WAN (default route) - aturan TIDAK diubah." >&2
  exit 1
fi

# IPv4
iptables -F DOCKER-USER 2>/dev/null || true
iptables -A DOCKER-USER -i lo -j RETURN
iptables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
for net in $CF4; do
  iptables -A DOCKER-USER -i "$WAN" -p tcp -m multiport --dports 80,443 -s "$net" -j RETURN
done
iptables -A DOCKER-USER -i "$WAN" -p tcp -m multiport --dports 80,443 -j DROP

# IPv6 (kalau tersedia)
if command -v ip6tables >/dev/null 2>&1 && [[ -n "$CF6" ]]; then
  ip6tables -F DOCKER-USER 2>/dev/null || true
  ip6tables -A DOCKER-USER -i lo -j RETURN
  ip6tables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  for net in $CF6; do
    ip6tables -A DOCKER-USER -i "$WAN" -p tcp -m multiport --dports 80,443 -s "$net" -j RETURN
  done
  ip6tables -A DOCKER-USER -i "$WAN" -p tcp -m multiport --dports 80,443 -j DROP
fi

echo "OK: port 80/443 dibatasi ke Cloudflare di interface $WAN ($(echo "$CF4" | wc -l) IPv4 + $(echo "$CF6" | wc -l) IPv6 range)"
echo "    Outbound container TIDAK dibatasi (rule hanya -i $WAN)."
