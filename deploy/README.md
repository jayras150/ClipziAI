# 🚀 Deploy Clipzi AI ke VPS (Hybrid: VPS + Vast.ai Serverless)

Panduan ini memasang **API (FastAPI) + frontend (Next.js) di satu VPS**, dengan
proses video berat dijalankan di **Vast.ai serverless GPU** (bayar per detik,
scale-to-zero).

```
Browser ──HTTPS──► Caddy (VPS)
                     ├── /api/*  ──► backend  :8000  (FastAPI)
                     └── /*      ──► frontend :3000  (Next.js)

backend ──► Supabase (PostgreSQL) / Upstash (Redis) / Cloudflare R2
backend ──► Vast.ai endpoint (GPU) ──► R2 + update status task di Postgres
```

Karena satu domain, **CORS tidak lagi jadi masalah**.

---

## ✅ Prasyarat

| Kebutuhan | Catatan |
|-----------|---------|
| VPS | minimal **1 vCPU / 1 GB RAM** (2 GB lebih nyaman), 20 GB disk, Ubuntu 22.04/24.04 atau Debian 12 |
| Domain | DNS **A record** sudah diarahkan ke IP VPS (wajib untuk HTTPS otomatis) |
| Image Docker | sudah di-push: `<user>/clipzi-backend` & `<user>/clipzi-frontend` (lihat README §Build & Upload Docker Hub) |
| Akun Vast.ai | sudah punya API key + kredit |
| `backend/.env` | sudah terisi (Supabase, Redis, R2, AI/transcription key) |

---

## 1. Arahkan domain ke VPS

Di panel DNS domain Anda:

```
A    clipzi    <IP_VPS>      TTL 300
```

Cek dari lokal (harus sudah menunjukkan IP VPS sebelum lanjut):

```bash
nslookup clipzi.domainanda.com
```

> Caddy butuh DNS valid + port 80/443 terbuka, kalau tidak sertifikat gagal terbit.

---

## 2. Pasang Docker di VPS

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl git

# Docker Engine + plugin compose
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

docker version
docker compose version
```

---

## 3. Tambah swap (WAJIB untuk VPS 1 GB)

```bash
sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

free -h            # pastikan baris Swap menunjukkan 2.0Gi
```

---

## 4. Ambil source code

```bash
cd ~
git clone <URL_REPO_ANDA> clipzi-ai
cd clipzi-ai
git checkout main
```

> Image diambil dari Docker Hub, jadi VPS **tidak** perlu build apa pun
> (build di VPS 1 GB akan kehabisan memori).

---

## 5. Siapkan konfigurasi

```bash
# 1) Rahasia backend
cp backend/.env.example backend/.env
nano backend/.env          # isi DATABASE_URL, REDIS_URL, R2_*, SECRET_KEY,
                           # ENCRYPTION_KEY, AI_API_KEY, TRANSCRIPTION_*, VAST_*

# 2) Konfigurasi deployment
cp deploy/.env.vps.example deploy/.env.vps
nano deploy/.env.vps       # isi DOMAIN, DOCKERHUB_USER, TAG, NEXT_PUBLIC_API_URL
```

Nilai penting di `backend/.env` untuk skenario satu domain:

```env
DEBUG=false
FRONTEND_URL=https://clipzi.domainanda.com
CORS_ORIGINS=https://clipzi.domainanda.com
TRANSCRIPTION_PROVIDER=groq          # atau openrouter/openai
TRANSCRIPTION_BASE_URL=https://api.groq.com/openai/v1
TRANSCRIPTION_MODEL=whisper-large-v3-turbo
YTDLP_COOKIES_BASE64=                # isi bila download kena bot-check
VAST_API_KEY=                        # atau pakai VAST_ENDPOINT_URL
VAST_ENDPOINT_NAME=clipzi-processing
```

---

## 6. Jalankan stack

```bash
cd ~/clipzi-ai
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml pull
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml up -d
```

Cek container:

```bash
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml ps
```

Harapan: `clipzi-api`, `clipzi-web`, `clipzi-caddy` semuanya **Up** (backend
menjadi `healthy` setelah ±40 detik).

---

## 7. Verifikasi

```bash
# 1) Backend lewat domain (HTTPS otomatis)
curl https://clipzi.domainanda.com/api/health
#    -> {"status":"healthy","redis":"connected",...}

# 2) Frontend + injeksi runtime env
curl https://clipzi.domainanda.com/runtime-env.js
#    -> window.__ENV__ = { NEXT_PUBLIC_API_URL: "https://clipzi.domainanda.com" };

# 3) Halaman utama
curl -I https://clipzi.domainanda.com
#    -> HTTP/2 200
```

Kalau `curl` gagal dengan sertifikat, lihat log Caddy:

```bash
docker logs clipzi-caddy --tail 50
```

Penyebab umum: DNS belum propagasi, port 80/443 terblokir firewall VPS.

---

## 8. Siapkan GPU worker di Vast.ai

Worker menjalankan **image backend yang sama** dengan entrypoint berbeda
(`deployments.worker_api:app`), lalu didaftarkan sebagai endpoint serverless.

```bash
# di mesin lokal (butuh: pip install vastai)
export VAST_API_KEY=...           # https://cloud.vast.ai/account/

python scripts/vastai-setup.py --help
python scripts/vastai-setup.py create     # buat endpoint + workergroup
python scripts/vastai-setup.py status     # lihat endpoint & worker
python scripts/vastai-setup.py logs       # log endpoint
```

Setelah endpoint aktif, ambil URL-nya lalu isi di `backend/.env`:

```env
# Mode HTTP (paling sederhana): API POST ke {URL}/process
VAST_ENDPOINT_URL=https://<endpoint>.run.vast.ai
```

atau pakai mode SDK (tanpa URL, butuh paket `vastai` di image API):

```env
VAST_API_KEY=...
VAST_ENDPOINT_NAME=clipzi-processing
```

Restart backend setelah mengubah env:

```bash
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml up -d backend
```

Cek mode dispatch yang aktif dari log:

```bash
docker logs clipzi-api --tail 50 | grep -i dispatch
```

| Log | Arti |
|-----|------|
| `mode dispatch=http` | API mengirim job ke `VAST_ENDPOINT_URL` |
| `mode dispatch=sdk` | API memakai SDK Vast (`queue_endpoint_request`) |
| `mode dispatch=inline` | Tidak ada konfigurasi Vast → pipeline jalan di proses API (hanya untuk dev) |

> **Catatan `inline`:** di VPS 1 GB, mode ini akan memproses video memakai CPU
> VPS (lambat) dan berisiko OOM. Untuk production selalu isi `VAST_ENDPOINT_URL`
> atau `VAST_API_KEY`.

---

## 9. Operasional harian

```bash
COMPOSE="docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml"

$COMPOSE logs -f backend      # log API
$COMPOSE logs -f caddy        # log akses + sertifikat
$COMPOSE restart backend      # setelah ubah backend/.env
docker stats                  # pemakaian RAM/CPU real-time
```

**Update ke versi image baru:**

```bash
cd ~/clipzi-ai
git pull
# ubah TAG di deploy/.env.vps kalau perlu (mis. 1.0.1)
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml pull
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml up -d
```

**Backup yang perlu disimpan** (kecil, cukup di-copy ke lokal):

| File | Isi |
|------|-----|
| `backend/.env` | seluruh rahasia |
| `deploy/.env.vps` | domain + tag image |
| `deploy/Caddyfile` | konfigurasi proxy (kalau diubah) |

Data pengguna **tidak** ada di VPS — semuanya di Supabase/Redis/R2.

---

## 🚚 Migrasi / Upgrade VPS

Karena **tidak ada data permanen di VPS**, migrasi hanya memindahkan 3 file
konfigurasi. Downtime realistis: **1–3 menit**.

### A. Siapkan VPS baru (paralel, VPS lama tetap jalan)

```bash
# di VPS BARU
sudo apt update && sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

# swap (wajib bila RAM 1 GB)
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

git clone <URL_REPO_ANDA> clipzi-ai && cd clipzi-ai
```

### B. Pindahkan konfigurasi dari VPS lama

Dari komputer Anda (bukan dari VPS lama):

```bash
scp user@VPS_LAMA:~/clipzi-ai/backend/.env         ./backend.env.bak
scp user@VPS_LAMA:~/clipzi-ai/deploy/.env.vps      ./vps.env.bak
scp user@VPS_LAMA:~/clipzi-ai/deploy/Caddyfile     ./Caddyfile.bak
```

Lalu kirim ke VPS baru:

```bash
scp ./backend.env.bak user@VPS_BARU:~/clipzi-ai/backend/.env
scp ./vps.env.bak     user@VPS_BARU:~/clipzi-ai/deploy/.env.vps
scp ./Caddyfile.bak   user@VPS_BARU:~/clipzi-ai/deploy/Caddyfile
```

> Volume `clipzi_cache` **tidak perlu** dipindahkan: cookie pool tersimpan di
> database dan akan di-decode ulang otomatis di worker/VPS baru.

### C. Jalankan di VPS baru (belum ganti DNS)

```bash
cd ~/clipzi-ai
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml pull
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml up -d

# uji langsung via IP (Caddy belum punya sertifikat untuk IP, jadi uji port internal)
curl http://127.0.0.1:8000/api/health   # di dalam VPS (docker exec)
docker exec clipzi-api curl -fsS http://127.0.0.1:8000/api/health
```

### D. Pindahkan domain

1. Turunkan TTL DNS ke **60 detik** (lakukan ≥1 jam sebelumnya agar propagasi cepat)
2. Ubah **A record** domain → **IP VPS BARU**
3. Tunggu propagasi, lalu uji:

```bash
curl https://clipzi.domainanda.com/api/health
curl https://clipzi.domainanda.com/runtime-env.js
```

Caddy di VPS baru akan menerbitkan sertifikat HTTPS baru secara otomatis.

### E. Matikan VPS lama (setelah yakin)

```bash
# di VPS LAMA
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml down
```

### Rollback (kalau ada masalah)

Arahkan kembali A record ke **IP VPS lama**, jalankan `up -d` di sana. Karena
state ada di Postgres/Redis/R2, tidak ada data yang hilang di kedua arah.

### Checklist migrasi

- [ ] DNS A record domain sudah diarahkan ke IP baru
- [ ] `backend/.env` & `deploy/.env.vps` tersalin (termasuk `VAST_*`)
- [ ] Port 80/443 VPS baru terbuka
- [ ] `https://domain/api/health` → `healthy` + `redis: connected`
- [ ] `https://domain/runtime-env.js` → URL domain yang benar
- [ ] Login + buat 1 task uji → status berubah `queued → processing → completed`
- [ ] VPS lama dimatikan

---

## 🧰 Troubleshooting

| Gejala | Penyebab & solusi |
|--------|-------------------|
| Caddy log: `failed to obtain certificate` | DNS belum mengarah ke IP VPS, atau port 80/443 tertutup |
| `502 Bad Gateway` di halaman | Container backend/frontend belum siap → `docker compose ps`, `docker logs clipzi-api` |
| Backend `unhealthy` terus | Cek `docker logs clipzi-api`: biasanya env wajib kosong (`DATABASE_URL`, `SECRET_KEY`, `R2_*`) |
| Halaman memanggil `localhost:8000` | `NEXT_PUBLIC_API_URL` salah/kosong → perbaiki `deploy/.env.vps`, lalu `up -d frontend` |
| Task tertahan di `queued` | Dispatch gagal / endpoint Vast belum siap → cek log `dispatch`, `VAST_ENDPOINT_URL`, `python scripts/vastai-setup.py status` |
| Container di-kill (OOM) | `dmesg \| tail` untuk konfirmasi; tambah swap, atau naikkan `mem_limit` |
| RAM penuh | `docker stats`; kalau frontend berat, pertimbangkan static export (`output: 'export'`) |
| `too many connections` (Supabase) | Kurangi `pool_size` engine, atau gunakan session pooler port 5432 |


