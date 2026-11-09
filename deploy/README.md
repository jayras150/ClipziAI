# 🚀 Deploy Clipzi AI ke VPS (Hybrid: VPS + Vast.ai Serverless)

> ## Status deployment aktif (production)
>
> | Item | Nilai |
> |------|-------|
> | Domain | `https://proxyai.live` (DNS A → `43.167.162.69`) |
> | VPS | Ubuntu 22.04, 2 vCPU, 3.7 GB RAM, 50 GB disk (+ swap 2 GB) |
> | Folder app | `/opt/clipzi/app` (symlink `/root/ClipziAI`) |
> | Compose | `/opt/clipzi/app/docker-compose.vps.yml` |
> | Container | `clipzi-api` (backend), `clipzi-web` (frontend), `clipzi-caddy` |
> | Image | backend dari Docker Hub `sujinwo555/clipzi-backend:1.5.0`; **frontend dibangun di VPS** |
> | Secrets | `/opt/clipzi/app/backend/.env` (chmod 600) |
>
> ```bash
> cd /opt/clipzi/app
> git pull
> docker compose -f docker-compose.vps.yml pull backend      # backend dari registry
> docker compose -f docker-compose.vps.yml build frontend    # frontend build lokal (±5-10 mnt)
> docker compose -f docker-compose.vps.yml up -d
> docker compose -f docker-compose.vps.yml ps
> docker logs --tail 50 clipzi-api
> curl -fsS https://proxyai.live/api/health
> ```
>
> Catatan: build frontend di 2 vCPU sebaiknya di `tmux`
> (`tmux new -d -s build 'docker compose -f docker-compose.vps.yml build frontend > /root/build.log 2>&1'`);
> `NEXT_PUBLIC_API_URL` di-inject saat container start, jadi ganti domain cukup
> ubah `environment:` di compose lalu `up -d` (tanpa rebuild).


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

Worker menjalankan **image backend yang sama**, hanya berbeda peran
(`CLIPZI_ROLE=worker` → `uvicorn deployments.worker_api:app`).

### 8.1 Apa itu "template" dan kenapa perlu?

Di Vast.ai, **template = pembungkus perintah `docker run`**. Isinya:

| Field template | Nilai untuk Clipzi | Kenapa |
|----------------|--------------------|--------|
| Image Path:Tag | `<user>/clipzi-backend:1.0.0` | image worker yang sudah kamu push |
| Docker options | `-p 8000:8000 -e CLIPZI_ROLE=worker` | buka port worker + pilih peran worker |
| Disk space | `40` GB | ruang unduh video + render sementara |
| Launch mode | Docker ENTRYPOINT (default) | entrypoint image sudah memilih peran |

Workergroup (pool worker) butuh **template** (`--template_hash`) **atau**
filter GPU langsung (`--search_params`). Jadi ada 2 cara:

### 8.2 CARA A — tanpa template (paling cepat, 2 menit)

Cukup isi **satu** variabel dengan image Docker Hub kamu:

```env
# backend/.env
VAST_WORKER_IMAGE=budi/clipzi-backend:1.0.0
VAST_TEMPLATE_HASH=
```

Script akan mengirim image lewat `launch_args` (`--image ...`) dan filter GPU
lewat `search_params`. Cocok untuk uji coba pertama.

### 8.3 CARA B — dengan template (disarankan untuk produksi)

**Lewat script (otomatis):**

```bash
# di mesin lokal, dari root repo
export VAST_API_KEY=...            # https://cloud.vast.ai/account/
pip install vastai                 # CLI resmi wajib ada
vastai set api-key "$VAST_API_KEY"

# 1) isi image di backend/.env
#    VAST_WORKER_IMAGE=budi/clipzi-backend:1.0.0

# 2) buat template -> script mencetak hash
python scripts/vastai-setup.py template
#   === Membuat template 'clipzi-worker' ===
#   > vastai create template --name clipzi-worker --image budi/clipzi-backend:1.0.0 \
#           --env '-p 8000:8000 -e CLIPZI_ROLE=worker' --disk_space 40 ...
#   === Mencari hash template ===
#     hash : 79ebdd2ebfb9d42cedf7a221c42d37a5
#     Tambahkan ke backend/.env:
#       VAST_TEMPLATE_HASH=79ebdd2ebfb9d42cedf7a221c42d37a5
```

**Lewat web console (kalau lebih nyaman klik):**

1. Buka **[cloud.vast.ai/templates](https://cloud.vast.ai/templates)** → tombol **+ New**
2. **Template Name**: `clipzi-worker`
3. **Image Path:Tag**: `docker.io/<user>/clipzi-backend:1.0.0`
   (untuk Docker Hub boleh tanpa `docker.io/`)
4. **Docker options**: isi persis
   ```
   -p 8000:8000 -e CLIPZI_ROLE=worker
   ```
5. **Disk Space**: `40`
6. **Launch Mode**: biarkan **Docker ENTRYPOINT** (jangan SSH/Jupyter)
7. **Save**, lalu buka kartu template itu — **hash** tertulis di sana
   (32 karakter hex, mis. `79ebdd2ebfb9d42cedf7a221c42d37a5`)
8. Isi ke `backend/.env`:
   ```env
   VAST_TEMPLATE_HASH=79ebdd2ebfb9d42cedf7a221c42d37a5
   ```

> **Cari hash lagi nanti** (kalau lupa):
> ```bash
> vastai search templates           # daftar template, lihat kolom hash_id
> vastai search templates --raw     # JSON (field `hash_id`)
> ```
> atau buka halaman template di console dan salin dari kartunya.

### 8.4 Buat endpoint + workergroup

```bash
python scripts/vastai-setup.py create     # idempotent: lewati endpoint yang sudah ada
python scripts/vastai-setup.py status     # lihat URL endpoint, state, jumlah worker
python scripts/vastai-setup.py activate   # kalau state=stopped -> aktifkan
python scripts/vastai-setup.py logs       # log endpoint
```

> **Catatan penting:** di Vast.ai, **workergroup tidak punya perintah start/stop**
> (`vastai update workergroup` hanya mengubah template/search/launch). Yang
> mengendalikan hidup-matinya worker adalah **endpoint**.

| Aksi | Perintah | Efek pada worker & tagihan |
|------|----------|---------------------------|
| Mulai / aktifkan | `vastai-setup.py activate` | Engine mulai menaikkan worker sesuai trafik. GPU ditagih saat worker `Ready`/`Loading` |
| **Stop** (GPU berhenti) | `vastai-setup.py activate --stop` | Semua worker jadi `Inactive`: **GPU tidak ditagih**, storage + bandwidth tetap |
| Suspend (engine diam) | `vastai-setup.py activate --suspend` | Engine berhenti mengelola, tapi worker yang sudah `Ready` **tetap hidup & ditagih** |
| Paksa 0 worker | `vastai-setup.py update --max-workers 0` | Batas atas worker = 0 (endpoint tetap aktif) |
| Hapus permanen | `vastai-setup.py teardown` | Workergroup + endpoint dihapus, seluruh tagihan worker berhenti |

Jadi: **"stop workergroup" = `activate --stop`** (endpoint `stopped`), bukan perintah
`workergroup` tersendiri. Untuk mengaktifkan kembali cukup `activate`.

### 8.4b Alternatif: Vast Deployments (`@remote`)

Selain worker HTTP, tersedia jalur **Vast Deployments** di
`backend/deployments/app.py`. SDK mem-package kode, membuat endpoint+workergroup
otomatis, lalu memanggil fungsi Python remote:

```bash
pip install vastai
export VAST_API_KEY=...
python -m deployments.app          # siapkan/selaraskan deployment
```

API yang dipakai di file itu sudah diverifikasi terhadap SDK `vastai` asli
(`Deployment.remote`, `.context`, `.image`, `.configure_autoscaling`,
`.async_ensure_ready`). Untuk produksi sehari-hari, **worker HTTP lebih sederhana**
dan sudah diuji end-to-end.

### 8.4c Mode "satu task satu instance" (create → run → destroy)

Selain endpoint serverless (8.4), ada pola **ephemeral instance**: satu instance
dibuat untuk satu task, lalu **dihapus** begitu task selesai sehingga tagihan GPU
berhenti total. Skripnya: `scripts/vastai-run-once.py`.

> 💡 Pola ini juga bisa dijalankan **otomatis oleh API** tanpa skrip:
> set `VAST_DISPATCH_MODE=oneshot` di `backend/.env` (lihat tabel dispatch di
> akhir bagian 8.5). Skrip di bawah cocok untuk task manual/batch.

```bash
# 1) sekali saja: dorong secret ke Environment Variables akun Vast
#    (JANGAN lewat --env di CLI: argumen terlihat di process list)
python scripts/vastai-run-once.py --task-id <UUID> --push-env --dry-run   # lihat dulu
python scripts/vastai-run-once.py --task-id <UUID> --push-env

# 2) jalankan satu task
python scripts/vastai-run-once.py --task-id <UUID>
python scripts/vastai-run-once.py --task-id <UUID> --max-price 0.40   # batas $/jam
python scripts/vastai-run-once.py --task-id <UUID> --keep             # jangan dihapus
```

Alur yang dijalankan skrip:

```
vastai search offers --raw "<VAST_GPU_FILTER>"      # pilih offer termurah
   ↓
vastai create instance <OFFER> --image <VAST_WORKER_IMAGE> \
        --env '-e CLIPZI_ROLE=worker' --onstart <script> --disk 40
   ↓  (onstart: cd /app && python -c "... run_video_pipeline(UUID) ...")
polling tabel tasks di PostgreSQL sampai status completed / error
   ↓
vastai destroy instance <ID> -y        # GPU berhenti ditagih
```

Bandingkan tiga mode:

| Mode | Siapa yang membuat/menghapus worker | Cold start | Biaya idle GPU | Cocok untuk |
|------|-------------------------------------|------------|----------------|-------------|
| **Endpoint + scale-to-zero** (8.4, default) | engine Vast otomatis | ~1–3 menit | 0 (setelah `inactivity_timeout`) | produksi: banyak user, antrean |
| **One-shot instance** (8.4c) | `vastai-run-once.py` | ~2–5 menit | 0 | task besar/langka, batch harian, eksperimen |
| **Inline** (dev) | — | 0 | — | lokal, tanpa GPU |

> **Penting:** menghapus instance setelah selesai **bisa** dilakukan, tapi jangan
> membuat instance baru di dalam request HTTP "start clip". `create instance`
> butuh ~2–5 menit (scheduling + pull image 2–3 GB) sehingga request user akan
> timeout. Karena itu:
> - **produksi** → pakai endpoint scale-to-zero; atur
>   `VAST_INACTIVITY_TIMEOUT=60` agar worker hilang ~1 menit setelah job terakhir;
> - **one-shot** → dipicu manual/cron dari luar API (skrip di atas), task-nya
>   sudah ada di DB sehingga user boleh menutup browser.

Perintah manual yang setara (tanpa skrip):

```bash
vastai search offers --raw "gpu_ram>=16 disk_space>=40 rentable=true num_gpus=1" | head -40
vastai create instance <OFFER_ID> --image budi/clipzi-backend:1.0.0 --disk 40 \
        --env '-e CLIPZI_ROLE=worker' --label clipzi-manual --cancel-unavail
vastai show instances                      # tunggu status "running"
vastai destroy instance <INSTANCE_ID> -y   # setelah selesai
```

**Wajib: reaper.** Kalau skrip/backend mati di tengah jalan, instance bisa
tertinggal hidup dan terus ditagih. Cek berkala:

```bash
vastai show instances --raw | grep -o '"label": "clipzi-[^"]*"'   # instance Clipzi
# hapus semua yang labelnya clipzi-* dan sudah tidak dipakai:
vastai destroy instance <ID> -y
```

Atau jadwalkan cron harian di VPS untuk memeriksa instance berlabel `clipzi-*`
yang `uptime` > 2 jam.


| Variabel | Wajib? | Contoh | Fungsi |
|----------|--------|--------|--------|
| `VAST_API_KEY` | ✅ | `abc123...` | autentikasi ke Vast.ai |
| `VAST_ENDPOINT_NAME` | ✅ | `clipzi-processing` | nama endpoint (unik per akun) |
| `VAST_WORKER_IMAGE` | ✅ (salah satu) | `budi/clipzi-backend:1.0.0` | image worker; dipakai saat membuat template / mode tanpa template |
| `VAST_TEMPLATE_HASH` | ⭐ disarankan | `79ebdd2ebfb9...` | template worker (hasil langkah 8.3) |
| `VAST_ENDPOINT_URL` | ⭐ | `https://xxxx.run.vast.ai` | URL endpoint; kalau diisi, API memakai mode HTTP |
| `VAST_GPU_FILTER` | — | `gpu_ram>=16 disk_space>=40` | filter GPU (dipakai bila tanpa template) |
| `VAST_MAX_WORKERS` | — | `4` | batas worker paralel |
| `VAST_INACTIVITY_TIMEOUT` | — | `300` | detik idle → scale-to-zero |

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
| `mode dispatch=oneshot` | API **membuat instance GPU** untuk task ini lalu **menghapusnya** setelah selesai |
| `mode dispatch=inline` | Tidak ada konfigurasi Vast → pipeline jalan di proses API (hanya untuk dev) |

#### Mode `oneshot` (instance dibuat & dihapus otomatis per task)

Skenario "user klik start → backend menyalakan GPU → selesai → instance dihapus"
tersedia langsung dari API. Aktifkan:

```env
# backend/.env
VAST_DISPATCH_MODE=oneshot
VAST_API_KEY=...
VAST_WORKER_IMAGE=budi/clipzi-backend:1.0.0     # atau VAST_TEMPLATE_HASH
VAST_ONESHOT_MAX_PRICE=0.40                     # 0 = tanpa batas ($/jam)
VAST_ONESHOT_TIMEOUT=3600                       # umur maksimum instance
VAST_ONESHOT_BOOT_TIMEOUT=900                   # gagal boot -> task error + instance dihapus
```

Alur: `POST /api/tasks` → API memilih offer termurah (`search_offers`) →
`create_instance(onstart_cmd=run_video_pipeline(task_id))` → API langsung membalas
`202/data task` (tidak menunggu GPU) → reaper memantau tabel `tasks` → begitu
status `completed`/`error`/`cancelled` (atau timeout) → `destroy_instance`.

Yang perlu diperhatikan:

| Hal | Detail |
|-----|--------|
| Waktu tunggu user | ~2–5 menit sebelum worker mulai memproses (scheduling + pull image) |
| Isolasi data | secret dibaca dari **Environment Variables akun Vast**, tidak lewat argumen |
| Biaya | GPU ditagih per detik selama instance hidup; setelah `destroy` = 0 |
| Risiko | API mati total → instance bisa yatim. Mitigasi: saat API start, `cleanup_orphan_instances()` menghapus instance `clipzi-*` yang task-nya sudah terminal/hilang. Cek manual: `vastai show instances` |

#### Worker tidak pernah `ready` (`failed to find rdy worker`)

Gejala di `python scripts/vastai-setup.py logs`:

```
error queue_work: endpoint 43832 failed to find rdy worker for req: ... new_load: 0
```

Instance naik (`loading` → `model_loading`) tetapi tidak pernah `ready`, sehingga
request menggantung lalu timeout. Penyebab yang sudah terbukti di Clipzi:

| Penyebab | Cara memastikan | Perbaikan |
|----------|-----------------|-----------|
| Workergroup masih memakai template lama (image `clipzy-worker`, port 8080) | `vastai show workergroups --raw` → lihat `template_hash`, `template_id`, `search_query.image_tag` | buat template baru + `python scripts/vastai-setup.py retemplate --hash <hash>` |
| Worker tidak memakai **PyWorker** | worker berhenti di `model_loading` walau container `running` | image worker harus `python -m deployments.pyworker_main` (`CLIPZI_ROLE=worker`) |
| Port PyWorker tidak diekspos | template env bukan `-p 8000:8000` | template env: `-p 8000:8000 -e CLIPZI_ROLE=worker -e WORKER_PORT=8000 -e MODEL_SERVER_PORT=18000` |
| `KeyError: VAST_TCP_PORT_8000` / `CONTAINER_ID` / `REPORT_ADDR` di log worker | port 8000 tidak dipetakan, atau worker dijalankan di luar instance Vast | pastikan template memetakan 8000→8000 (Vast lalu membuat env `VAST_TCP_PORT_8000` dkk) |
| `Missing EndpointHandler with BenchmarkConfig` | log worker saat start | harus ada tepat satu `HandlerConfig(benchmark_config=...)`; Clipzi memakai route murah `/ping` |
| PyWorker tidak pernah mendeteksi model siap | `MODEL_LOG_FILE` tidak bisa dibaca user container | gunakan default `/app/tmp/model-server.log` (dimiliki user non-root `clipzi`) |
| Template privat dibuat tapi hash tidak tercatat | `VAST_TEMPLATE_HASH` kosong | pakai hash dari keluaran `vastai-setup.py template` (kini dibaca dari keluaran `create`, bukan dari pencarian publik) |

Alur perbaikan lengkap:

```bash
# 0. hentikan biaya dulu
python scripts/vastai-setup.py activate --stop

# 1. build & push ulang image worker (kode PyWorker ikut di dalam image)
docker build -t <user>/clipzi-backend:1.1.0 backend
docker push <user>/clipzi-backend:1.1.0
#    lalu set VAST_WORKER_IMAGE=<user>/clipzi-backend:1.1.0 di backend/.env

# 2. template baru + arahkan workergroup ke template itu
python scripts/vastai-setup.py template
python scripts/vastai-setup.py retemplate --hash <hash-dari-langkah-2>

# 3. nyalakan & uji
python scripts/vastai-setup.py activate
python scripts/vastai-setup.py logs --tail 50     # tunggu worker `ready`
python scripts/vastai-smoke-test.py --send        # 1 request /health; harus OK
```

| Kapan dipakai | task besar/langka, batch malam, demo. Untuk trafik ramai pakai endpoint scale-to-zero |


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


