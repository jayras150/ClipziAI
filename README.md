# Clipzi AI

**Ubah Video Panjang → Shorts Viral dalam 1 Klik**

🇮🇩 **Bahasa Indonesia** · [🇬🇧 English](README.en.md)

Full-stack platform: FastAPI (backend) + Next.js 14 (frontend), dengan AI untuk
viral scoring, auto subtitle, smart crop 9:16, dan auto-upload ke YouTube.

| Item | Nilai |
|------|-------|
| Versi | 1.0.0 |
| Backend | Python 3.11/3.12 · FastAPI 0.115.6 · SQLAlchemy 2.0 (async) |
| Frontend | Next.js 14.2 · React 18 · TypeScript 5.9 · TailwindCSS |
| Database | PostgreSQL (Supabase) — 31 tabel |
| Cache / Queue | Redis (Upstash) |
| Object Storage | Cloudflare R2 |
| API Endpoint | 63 path (lihat `GET /openapi.json`) |
| Container | 2 image terpisah: `clipzi-backend`, `clipzi-frontend` |

---

## 📑 Daftar Isi

1. [Arsitektur](#-arsitektur)
2. [Struktur Repository](#-struktur-repository)
3. [Fitur Utama](#-fitur-utama)
4. [Prasyarat](#-prasyarat)
5. [Quick Start (lokal)](#-quick-start-lokal)
6. [Konfigurasi Environment](#-konfigurasi-environment)
7. [🐳 Build & Push Docker Image](#-build--push-docker-image) ← **panduan lengkap**
8. [Menjalankan Container](#-menjalankan-container)
9. [Deploy ke Vast.ai](#-deploy-ke-vastai)
10. [Provider AI & Transkripsi](#-provider-ai--transkripsi)
11. [Cookies yt-dlp & Rotasi Otomatis](#-cookies-yt-dlp--rotasi-otomatis)
12. [Database & Migrasi](#-database--migrasi)
13. [Redis (Upstash)](#-redis-upstash)
14. [API Reference](#-api-reference)
15. [Paket Harga](#-paket-harga)
16. [Keamanan](#-keamanan)
17. [Integrasi Android](#-integrasi-android)
18. [Troubleshooting](#-troubleshooting)
19. [Kontribusi & Lisensi](#-kontribusi--lisensi)

---

## 🏗 Arsitektur

```
┌──────────────────┐        HTTPS/JSON        ┌────────────────────┐
│  Frontend        │ ───────────────────────► │  Backend           │
│  Next.js :3000   │ ◄─────────────────────── │  FastAPI :8000     │
└────────┬─────────┘      (JWT Bearer)        └─────────┬──────────┘
         │                                              │
         │ URL file publik                              ├──► PostgreSQL (Supabase)
         ▼                                              ├──► Redis (Upstash)
┌──────────────────┐                                    └──► Cloudflare R2
│  Cloudflare R2   │  ◄── upload hasil render
└──────────────────┘
```

Aplikasi bersifat **stateless** — tidak menyimpan state di server mana pun:

| Data | Disimpan di |
|------|-------------|
| User, task, klip, kredit, langganan | PostgreSQL (Supabase) |
| Cache, rate limit, progress | Redis (Upstash) |
| Video & file hasil render | Cloudflare R2 |
| Sesi login | JWT di `localStorage` browser |

Konsekuensinya: frontend dan backend **boleh berjalan di mesin berbeda**, dan
restart backend tidak membuat user logout.

---

## 📁 Struktur Repository

```
ClipziAI/
├── backend/
│   ├── app/
│   │   ├── api/            # router publik + admin
│   │   ├── core/           # config, security (AES-GCM), redis
│   │   ├── db/             # engine async + init_db()
│   │   ├── models/         # 31 model SQLAlchemy
│   │   ├── schemas/        # Pydantic
│   │   └── services/       # AI, transcriber, downloader, cookie_store, storage
│   ├── alembic/            # (belum ada migration — lihat §Database)
│   ├── Dockerfile          # image backend (multi-stage)
│   ├── requirements.txt    # versi dipin (lihat catatan)
│   └── .env.example
├── frontend/
│   ├── src/app/            # App Router (page, login, register, dashboard)
│   ├── src/lib/            # api client, env runtime, i18n
│   ├── src/types/          # deklarasi *.css / aset
│   ├── public/             # runtime-env.js (dibuat container)
│   ├── Dockerfile          # image frontend (standalone)
│   └── docker-entrypoint.sh
├── scripts/
│   ├── build-and-push.ps1  # build & push (Windows)
│   ├── build-and-push.sh   # build & push (Linux/macOS/Vast.ai)
│   ├── encode_cookies.py   # cookies.txt -> base64
│   ├── check_ytdlp_cookies.py  # health-check cookies (cron)
│   ├── seed_pricing.py
│   └── grant_signup_credits.py
├── docker-compose.yml       # dev: build dari source (backend+db+frontend)
├── docker-compose.prod.yml  # prod: pakai image dari Docker Hub
├── pyrightconfig.json       # Pylance: extraPaths + venv
└── .vscode/settings.json    # interpreter & TS SDK
```

---

## ✨ Fitur Utama

### Editing Video (30+ Fitur)
| Kategori | Fitur |
|----------|-------|
| **Framing** | Smart Crop 9:16, Blur Background, Contrast/Brightness |
| **Zoom** | Auto Zoom (Face), Auto Zoom (Audio), Ken Burns Effect |
| **Tracking** | Object Tracking |
| **Subtitle** | Auto Subtitle (Whisper), Karaoke, Animated Caption, Multi-language (30+), Title Card |
| **Audio** | Silence Removal, Background Music, Audio Ducking, Noise Reduction, Voice Enhancement, Sound Effects |
| **Visual** | Color Grading, Video Filters, Speed Ramp, Transitions |
| **Branding** | Custom Watermark, Sticker/Emoji, Progress Bar, Intro/Outro, End Screen |
| **AI** | Viral Scoring, AI Title & Tags, Thumbnail AI |

### Distribusi
- YouTube Upload (OAuth2, `access_type=offline` → refresh token tersimpan terenkripsi)
- Scheduled Publish (YouTube, TikTok, Instagram, Facebook)
- Multi-Platform Repurpose (satu video → banyak platform)
- Bulk Processing (satu video panjang → banyak klip)

### Akun & Pembayaran
- Login email/password (Argon2id) atau sosial (Google, X/Twitter, Facebook)
- 2FA TOTP + kode cadangan
- Paket: Free, Standar, Pro, Team
- Sistem kredit (5 kredit gratis saat daftar)
- Pembayaran Duitku + callback webhook
- Invoice otomatis (PDF)

### Keamanan & Admin
- Admin dashboard dengan RBAC (Super Admin, Admin, Moderator)
- Audit trail lengkap
- Enkripsi AES-256-GCM untuk field sensitif (mis. refresh token YouTube, cookies yt-dlp)
- Rate limiting berbasis Redis (per IP & per API key)
- Content moderation & copyright check
- GDPR/PDP compliance (export/hapus data)

---

## ✅ Prasyarat

| Kebutuhan | Versi | Catatan |
|-----------|-------|---------|
| Python | 3.11 / 3.12 | 3.11 dipakai di image Docker |
| Node.js | 20 LTS | untuk frontend |
| Docker Desktop | terbaru | **wajib berjalan** untuk build image |
| ffmpeg | opsional | hanya jika menjalankan backend tanpa Docker |
| Akun Supabase / Upstash / Cloudflare R2 | — | atau Postgres+Redis lokal |

---

## 🚀 Quick Start (lokal)

### 1. Backend

```bash
cd backend

# 1. Buat virtualenv (sekali saja)
python -m venv .venv

# 2. Aktifkan
#    Windows PowerShell:
.venv\Scripts\Activate.ps1
#    Linux / macOS:
source .venv/bin/activate

# 3. Install dependency
pip install -r requirements.txt

# 4. Konfigurasi
cp .env.example .env
#   lalu isi DATABASE_URL, REDIS_URL, R2_*, SECRET_KEY, ENCRYPTION_KEY,
#   dan minimal satu AI_API_KEY

# 5. Seed paket harga (opsional tapi disarankan)
python ../scripts/seed_pricing.py

# 6. Jalankan
uvicorn app.main:app --reload --port 8000
```

Cek berhasil:

```bash
curl http://localhost:8000/api/health      # {"status":"healthy","redis":"connected",...}
# Dokumentasi interaktif: http://localhost:8000/docs
```

> ⚠️ **`requirements.txt` memakai versi yang dipin** (`fastapi==0.115.6`,
> `starlette==0.41.3`, `sqlalchemy==2.0.36`, dst). Jangan naikkan mayor tanpa
> uji ulang — FastAPI 0.16x / Starlette 1.x mengubah struktur `app.routes`.
> `sqlalchemy[asyncio]` wajib memakai extra `[asyncio]` agar `greenlet`
> terpasang; tanpa itu backend gagal start dengan `ImportError`.

### 2. Frontend

```bash
cd frontend
npm ci                 # gunakan ci agar sesuai package-lock.json
npm run dev            # http://localhost:3000
```

Frontend membaca `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
Saat dev, cukup buat `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Cek cepat seluruh stack

| Cek | Perintah | Harapan |
|-----|----------|---------|
| Backend hidup | `curl localhost:8000/api/health` | `status: healthy` |
| Redis nyambung | response di atas | `redis: connected` |
| Frontend hidup | buka `localhost:3000` | landing page tampil |
| Login | buka `/register` | user baru dapat 5 kredit |

---

## ⚙️ Konfigurasi Environment

Semua konfigurasi backend ada di **satu file**: `backend/.env`
(salin dari `backend/.env.example`). File `.env` **tidak pernah** ikut ter-commit
atau masuk ke Docker image — nilainya diberikan saat container dijalankan.

### Variabel wajib (backend tidak mau start tanpa ini)

| Variabel | Contoh | Keterangan |
|----------|--------|-----------|
| `SECRET_KEY` | `fe3b37...` (64 hex) | tanda tangan JWT. Generate: `python -c "import secrets;print(secrets.token_hex(32))"` |
| `ENCRYPTION_KEY` | `368984...` (64 hex) | AES-256-GCM untuk field sensitif |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/postgres` | **wajib** prefix `postgresql+asyncpg://` |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | URL project (bukan key) |
| `SUPABASE_KEY` | `sb_secret_...` | server key, jangan dipakai di frontend |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | — | Cloudflare R2 |
| `R2_ENDPOINT_URL` | `https://<account>.r2.cloudflarestorage.com` | |
| `R2_BUCKET_NAME` | `files` | |
| `R2_PUBLIC_DOMAIN` | `https://pub-xxxx.r2.dev` | domain publik file |

### Variabel penting lainnya

| Variabel | Default | Keterangan |
|----------|---------|-----------|
| `DEBUG` | `true` | **set `false` di produksi** — `DEBUG=true` membuat SQLAlchemy mencatat semua query (lambat + bocor data ke log) |
| `FRONTEND_URL` | `http://localhost:3000` | tujuan redirect setelah OAuth YouTube |
| `CORS_ORIGINS` | `http://localhost:3000` | daftar origin frontend, pisah koma. Harus **persis** (skema+host+port) |
| `API_KEY_PREFIX` | `clipzy_` | prefix API key user. Isi prefix saja, bukan contoh lengkap |
| `REDIS_URL` | `redis://localhost:6379/0` | Upstash: `rediss://default:<pass>@<db>.upstash.io:6379` |
| `AI_PROVIDER` | `openai` | `openai` / `groq` / `openrouter` / `together` / `deepseek` / `mistral` / `azure` / `ollama` / `custom` |
| `AI_API_KEY` | — | key provider LLM |
| `AI_BASE_URL` | — | opsional; Ollama: `http://localhost:11434/v1` |
| `AI_MODEL` | — | nama model di provider |
| `TRANSCRIPTION_PROVIDER` | `local` | `local` (faster-whisper) atau provider OpenAI-compatible |
| `TRANSCRIPTION_BASE_URL` | — | **harus root `/v1`**, bukan endpoint lengkap |
| `TRANSCRIPTION_MODEL` | — | mis. `whisper-1`, `whisper-large-v3-turbo` |
| `WHISPER_MODEL` | `small` | `tiny`/`base`/`small`/`medium`/`large-v3` (hanya untuk `local`) |
| `YOUTUBE_CLIENT_ID` / `_SECRET` | — | Google Cloud Console → OAuth 2.0 Client |
| `YOUTUBE_REDIRECT_URI` | `http://localhost:8000/api/youtube/callback` | harus sama dengan yang didaftarkan di Google |
| `YOUTUBE_API_KEY` | — | untuk akses data publik |
| `DUITKU_MERCHANT_CODE` / `DUITKU_API_KEY` | — | payment gateway |
| `DUITKU_CALLBACK_URL` | `.../api/payment/callback` | **harus URL publik**, bukan localhost |
| `GOOGLE_/X_/FACEBOOK_CLIENT_ID` & `_SECRET` | — | login sosial |
| `MAX_VIDEO_DURATION_MINUTES` | `120` | batas durasi input |
| `MAX_FILE_SIZE_MB` | `2000` | batas ukuran |
| `OUTPUT_FPS` / `OUTPUT_RESOLUTION` | `30` / `1080x1920` | output klip |
| `YTDLP_COOKIES_BASE64` / `_FILE` | — | cookies YouTube (lihat §Cookies) |
| `YTDLP_COOKIE_MAX_FAILURES` | `3` | rotasi cookies otomatis |
| `SMTP_*` | — | email transaksional |

### ⚠️ 5 jebakan konfigurasi yang sering terjadi

1. **`DATABASE_URL` pakai driver sync** (`postgresql://`) → engine async gagal
   (`ModuleNotFoundError: psycopg2`). Kode sudah menormalkan otomatis, tapi
   tetap tulis `postgresql+asyncpg://`.
2. **Port pooler Supabase**: `5432` = session pooler (cocok untuk asyncpg),
   `6543` = transaction pooler (hindari untuk prepared statements).
3. **`TRANSCRIPTION_BASE_URL` diisi endpoint lengkap**
   (`.../v1/audio/transcriptions`) → SDK menambah `/audio/transcriptions` lagi
   → **404**. Isi root `/v1` saja.
4. **`CORS_ORIGINS` tidak cocok** dengan origin frontend → browser memblokir
   dengan pesan *blocked by CORS policy*.
5. **`DEBUG=true` di produksi** → log penuh query + data pengguna.

### Callback URL untuk developer console

| Platform | Callback URL |
|----------|-------------|
| YouTube OAuth | `http://localhost:8000/api/youtube/callback` |
| Google Login | `http://localhost:8000/api/auth/google/callback` |
| X/Twitter Login | `http://localhost:8000/api/auth/x/callback` |
| Facebook Login | `http://localhost:8000/api/auth/facebook/callback` |
| Duitku | `https://<domain-publik>/api/payment/callback` |

> Google **menolak** redirect URI `http://` selain `localhost`. Untuk produksi
> wajib HTTPS + domain (reverse proxy / Cloudflare Tunnel).

---

## 🐳 Build & Push Docker Image

Clipzi memakai **dua image terpisah** agar bisa diskalakan & di-deploy sendiri-sendiri:

| Image | Base | Ukuran ± | Isi |
|-------|------|----------|-----|
| `clipzi-backend` | `python:3.11-slim` | 1.3–1.8 GB | FastAPI + uvicorn, ffmpeg, yt-dlp (binary terbaru), faster-whisper, OpenCV, user non-root `clipzi` (uid 10001), healthcheck `/api/health` |
| `clipzi-frontend` | `node:20-alpine` | ±180 MB | Next.js **standalone** output, entrypoint runtime-env, user non-root `nextjs` (uid 10001) |

### Prasyarat

```bash
docker version          # harus menampilkan versi Server, bukan error
docker login            # hanya jika akan push ke Docker Hub
```

> Jika muncul `failed to connect to the docker API ... dockerDesktopLinuxEngine`,
> **Docker Desktop belum jalan**. Nyalakan dulu, tunggu sampai status "Engine running".
> Tidak wajib build di laptop — bisa juga build langsung di instance Vast.ai
> (Docker sudah tersedia di sana).

### Struktur Dockerfile (multi-stage)

**Backend** (`backend/Dockerfile`) — 2 stage:

```
stage builder : python:3.11-slim + build-essential → venv di /opt/venv
stage runtime : python:3.11-slim + ffmpeg, libgl1, libsndfile1, libgomp1,
                yt-dlp binary, COPY --from=builder /opt/venv → user non-root
```

**Frontend** (`frontend/Dockerfile`) — 3 stage:

```
stage deps    : node:20-alpine → npm ci
stage builder : npm run build dengan ENV DOCKER_BUILD=1 → output standalone
stage runner  : copy .next/standalone + static + public → node server.js
```

`DOCKER_BUILD=1` membuat `next.config.js` memakai `output: "standalone"` hanya
saat build Docker, sehingga `npm run dev`/`npm start` di lokal tidak terpengaruh.

### Langkah 1 — Build image backend

```bash
# dari root repo
docker build -t clipzi-backend:1.0.0 -f backend/Dockerfile backend
```

Penjelasan tiap argumen:

| Argumen | Arti |
|---------|------|
| `-t clipzi-backend:1.0.0` | nama image + tag |
| `-f backend/Dockerfile` | lokasi Dockerfile |
| `backend` | **build context** — folder ini yang dikirim ke daemon; `.env` dikecualikan oleh `backend/.dockerignore` |

Untuk menargetkan arsitektur tertentu (mis. instance Vast.ai x86_64):

```bash
docker build --platform linux/amd64 \
  -t clipzi-backend:1.0.0 -f backend/Dockerfile backend
```

### Langkah 2 — Build image frontend

```bash
docker build -t clipzi-frontend:1.0.0 -f frontend/Dockerfile frontend
```

> `NEXT_PUBLIC_API_URL` **tidak** perlu diberikan saat build. Nilainya di-inject
> saat container dijalankan oleh `frontend/docker-entrypoint.sh` yang menulis
> `/app/public/runtime-env.js`. Jadi **satu image** bisa dipakai di lokal,
> server, maupun Vast.ai.

### Langkah 3 — (Opsional) build semua sekaligus dengan script

**Windows (PowerShell):**

```powershell
cd "C:\Users\WINDOWS 11 PRO\Documents\ClipziAI"
docker login
./scripts/build-and-push.ps1 -DockerHubUser <username-dockerhub> -Tag 1.0.0
```

**Linux / macOS / instance Vast.ai:**

```bash
./scripts/build-and-push.sh <username-dockerhub> 1.0.0
```

Parameter yang tersedia:

| PS1 | Bash (env) | Default | Fungsi |
|-----|-----------|---------|--------|
| `-DockerHubUser` | arg ke-1 | wajib | username Docker Hub (prefix nama image) |
| `-Tag` | arg ke-2 | `latest` | tag image |
| `-Platform` | `PLATFORM` | `linux/amd64` | target platform |
| `-BackendOnly` | `TARGET=backend` | — | hanya backend |
| `-FrontendOnly` | `TARGET=frontend` | — | hanya frontend |
| `-SkipPush` | `BUILD_ONLY=1` | — | build tanpa push |

Contoh build lokal saja (tanpa push):

```powershell
./scripts/build-and-push.ps1 -DockerHubUser budi -SkipPush
```

```bash
BUILD_ONLY=1 ./scripts/build-and-push.sh budi
```

### Langkah 4 — Push ke Docker Hub

```bash
docker login                     # sekali per mesin
docker push <user>/clipzi-backend:1.0.0
docker push <user>/clipzi-frontend:1.0.0
```

Tambahkan juga tag `latest` bila ingin dipakai sebagai default:

```bash
docker tag <user>/clipzi-backend:1.0.0  <user>/clipzi-backend:latest
docker tag <user>/clipzi-frontend:1.0.0 <user>/clipzi-frontend:latest
docker push <user>/clipzi-backend:latest
docker push <user>/clipzi-frontend:latest
```

> Di Docker Hub, buat repository **private** dulu bila image tidak untuk publik.
> Instance Vast.ai bisa pull image private selama kamu menyertakan kredensial
> (`docker login` di instance) atau memakai token.

### Langkah 5 — Verifikasi image

```bash
docker images | grep clipzi

# Backend: cek healthcheck & endpoint
docker run -d --rm --name test-api -p 8000:8000 \
  --env-file backend/.env <user>/clipzi-backend:1.0.0
sleep 5
curl http://localhost:8000/api/health
docker logs test-api
docker rm -f test-api

# Frontend: cek runtime env ter-inject
docker run -d --rm --name test-web -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://localhost:8000 \
  <user>/clipzi-frontend:1.0.0
sleep 5
curl http://localhost:3000/runtime-env.js
#   -> window.__ENV__ = { NEXT_PUBLIC_API_URL: "http://localhost:8000" };
docker rm -f test-web
```

Kalau `/runtime-env.js` menampilkan URL yang benar, image frontend sudah portabel.

### Tanpa Docker Hub (build di satu mesin, pindah ke mesin lain)

```bash
# di mesin sumber
docker save <user>/clipzi-backend:1.0.0 | gzip > clipzi-backend.tar.gz
scp clipzi-backend.tar.gz user@server:/tmp/

# di mesin tujuan
docker load < /tmp/clipzi-backend.tar.gz
```

### Tips build (hemat waktu & disk)

| Kebutuhan | Perintah |
|-----------|----------|
| Rebuild tanpa cache | `docker build --no-cache -t ... -f backend/Dockerfile backend` |
| Lihat layer & ukuran | `docker history <image>` |
| Bersihkan sisa build | `docker builder prune -f` |
| Bersihkan image tak terpakai | `docker image prune -f` |
| Build paralel dua image | jalankan `build-and-push` script (otomatis berurutan) |

### ⚠️ Troubleshooting build

| Gejala | Penyebab & solusi |
|--------|-------------------|
| `failed to connect to the docker API ... dockerDesktopLinuxEngine` | Docker Desktop belum jalan → nyalakan, tunggu "Engine running" |
| `pip install` gagal di stage builder | Cek koneksi; untuk proxy korporat set `--build-arg HTTP_PROXY=...` |
| Container backend langsung exit | Baca `docker logs <container>`. Umumnya `DATABASE_URL`/`SECRET_KEY` kosong, atau `greenlet` tidak ada (pastikan `sqlalchemy[asyncio]` — sudah ada di requirements) |
| `ModuleNotFoundError: No module named 'app'` | Build context salah — harus `backend`, bukan root repo |
| Frontend blank / API 404 | `NEXT_PUBLIC_API_URL` salah atau backend tidak reachable dari browser |
| Image terlalu besar | Backend ±1.5 GB wajar (OpenCV + faster-whisper + ffmpeg). Bisa dikecilkan dengan menghapus dependency tak terpakai dari `requirements.txt` |
| `exec format error` di Vast.ai | Image di-build untuk arsitektur beda → tambahkan `--platform linux/amd64` |

---

## ▶️ Menjalankan Container

### A. Dua container terpisah (paling umum)

```bash
# 1. Backend — semua rahasia dari file .env, tidak masuk image
docker run -d \
  --name clipzi-api \
  -p 8000:8000 \
  --env-file backend/.env \
  -v clipzi-cache:/app/.cache \
  --restart unless-stopped \
  <user>/clipzi-backend:1.0.0

# 2. Frontend — API URL bisa diganti kapan saja
docker run -d \
  --name clipzi-web \
  -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://IP_PUBLIK:8000 \
  --restart unless-stopped \
  <user>/clipzi-frontend:1.0.0
```

Catatan:

| Hal | Penjelasan |
|-----|-----------|
| `--env-file backend/.env` | file `.env` dibaca **saat runtime**, bukan dibundel |
| `-v clipzi-cache:/app/.cache` | menyimpan cache cookies yt-dlp agar token hasil rotasi tidak hilang saat container restart |
| `--restart unless-stopped` | auto-restart bila crash / server reboot |
| `-e NEXT_PUBLIC_API_URL=...` | ditulis ke `/app/public/runtime-env.js` saat start |

Perintah harian:

```bash
docker logs -f clipzi-api          # lihat log
docker inspect --format '{{.State.Health.Status}}' clipzi-api
docker restart clipzi-api          # ganti env -> cukup restart, tidak perlu rebuild
docker rm -f clipzi-api clipzi-web
```

### B. Docker Compose — dari source (development)

```bash
cp backend/.env.example backend/.env     # lalu isi kredensial
docker compose up -d --build             # backend + db(postgres) + frontend
docker compose logs -f backend
docker compose down
```

`docker-compose.yml` menjalankan Postgres lokal + (opsional) Redis lokal:

```bash
docker compose --profile local-redis up -d
# lalu set REDIS_URL=redis://redis:6379/0
```

### C. Docker Compose — dari image hasil push (production)

```bash
export DOCKERHUB_USER=<username-dockerhub>
export TAG=1.0.0
export NEXT_PUBLIC_API_URL=http://IP_PUBLIK:8000
docker compose -f docker-compose.prod.yml up -d
```

Isi `docker-compose.prod.yml`:

| Service | Image | Port | Env |
|---------|-------|------|-----|
| `backend` | `${DOCKERHUB_USER}/clipzi-backend:${TAG}` | 8000 | `env_file: ./backend/.env` |
| `frontend` | `${DOCKERHUB_USER}/clipzi-frontend:${TAG}` | 3000 | `NEXT_PUBLIC_API_URL` |

### D. Catatan kapasitas

- **Backend** bisa jalan **tanpa GPU**. `faster-whisper` di image memakai CPU (`int8`),
  cukup untuk `WHISPER_MODEL=small`.
- Untuk volume tinggi, pindahkan transkripsi ke provider cloud
  (`TRANSCRIPTION_PROVIDER=groq|openai`) sehingga CPU instance tetap ringan.

---

## 📦 Deploy ke Vast.ai

1. **Build & push image** dari mesin yang Docker-nya hidup:

   ```bash
   ./scripts/build-and-push.sh <user-dockerhub> 1.0.0
   ```

2. Buat akun di [vast.ai](https://vast.ai) → *Search* → pilih instance
   (CPU-only cukup untuk API + transkripsi cloud; GPU hanya bila ingin
   transkripsi lokal yang cepat).

3. Pada kolom **Image**, tempel:
   `<user-dockerhub>/clipzi-backend:1.0.0`

4. Pada **On-start script** (opsional), jalankan container otomatis:

   ```bash
   docker run -d --name clipzi-api -p 8000:8000 \
     --env-file /workspace/backend/.env \
     -v clipzi-cache:/app/.cache \
     --restart unless-stopped \
     <user-dockerhub>/clipzi-backend:1.0.0
   ```

5. Buka port **8000** (API) dan **3000** (frontend) di pengaturan instance.

6. Isi environment. Cara paling aman: upload `backend/.env` ke instance lalu
   gunakan `--env-file`. Alternatif: isi satu per satu di panel *Environment*.

7. Jalankan frontend dengan IP publik instance:

   ```bash
   docker run -d --name clipzi-web -p 3000:3000 \
     -e NEXT_PUBLIC_API_URL=http://<IP_PUBLIK>:8000 \
     <user-dockerhub>/clipzi-frontend:1.0.0
   ```

8. Verifikasi:

   ```bash
   curl http://<IP_PUBLIK>:8000/api/health
   curl http://<IP_PUBLIK>:3000/runtime-env.js
   ```

> ⚠️ **Penting untuk Vast.ai**
> - Disk instance bersifat **sementara** → hasil video wajib diarahkan ke
>   Cloudflare R2 (`R2_*`), jangan disimpan lokal.
> - IP datacenter sering diblokir YouTube → siapkan **cookies yt-dlp**
>   (lihat bagian berikut).
> - Google OAuth **menolak** redirect URI `http://IP` → untuk fitur connect
>   YouTube pakai domain + HTTPS (Cloudflare Tunnel / reverse proxy).

---

## 🤖 Provider AI & Transkripsi

### Provider LLM (viral scoring, judul, deskripsi, tag)

Satu konfigurasi untuk semua fitur AI — bisa ganti provider tanpa ubah kode.

```env
# Provider: openai | groq | openrouter | together | deepseek | mistral | azure | ollama | custom
AI_PROVIDER=groq
AI_API_KEY=gsk_your-key
AI_MODEL=llama-3.1-8b-instant
# AI_BASE_URL boleh kosong untuk provider bawaan.
AI_BASE_URL=
```

Contoh **Ollama lokal** (tanpa API key):

```env
AI_PROVIDER=ollama
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3.1
AI_API_KEY=
```

Untuk endpoint sendiri: `AI_PROVIDER=custom` + `AI_BASE_URL` (root `/v1`).
`OPENAI_API_KEY` hanya fallback kompatibilitas bila `AI_API_KEY` kosong.

### Provider Transkripsi

```env
# Lokal (faster-whisper, CPU int8)
TRANSCRIPTION_PROVIDER=local
WHISPER_MODEL=small
```

```env
# Cloud (harus kompatibel OpenAI /audio/transcriptions), mis. Groq
TRANSCRIPTION_PROVIDER=groq
TRANSCRIPTION_API_KEY=gsk_your-key
TRANSCRIPTION_BASE_URL=https://api.groq.com/openai/v1   # root /v1, BUKAN endpoint lengkap
TRANSCRIPTION_MODEL=whisper-large-v3-turbo
```

Urutan fallback API key: `TRANSCRIPTION_API_KEY` → `AI_API_KEY` → `OPENAI_API_KEY`.

| Model lokal | RAM ± | Akurasi | Kecepatan |
|-------------|-------|---------|-----------|
| `tiny` / `base` | ~1 GB | rendah–sedang | cepat |
| `small` | ~2 GB | bagus | seimbang |
| `medium` | ~5 GB | lebih bagus | agak lambat |
| `large-v3` | ~10 GB | terbaik | lambat |

---

## 🍪 Cookies yt-dlp & Rotasi Otomatis

yt-dlp **tidak** memakai cookies secara otomatis. Tanpa cookies, download tetap
jalan untuk **video publik dari IP residensial**, tetapi gagal di IP datacenter
(Vast.ai / VPS / cloud) dengan pesan:

```
Sign in to confirm you're not a bot
```

Isi cookies **hanya bila** menemui error itu, atau butuh video
age-restricted / private / member-only.

### Cara 1 — base64 (paling praktis untuk Docker)

```bash
# 1. Login YouTube di browser, pasang ekstensi "Get cookies.txt LOCALLY"
# 2. Export -> cookies.txt
# 3. Encode
python scripts/encode_cookies.py cookies.txt
```

Tempel hasilnya ke `backend/.env`:

```env
YTDLP_COOKIES_BASE64=H4sIAAAA...     # satu baris panjang
```

Backend men-decode ke `.cache/ytdlp_cookies.txt` saat pertama dipakai
(tidak ikut masuk image).

### Cara 2 — file (mount)

```env
YTDLP_COOKIES_FILE=/app/cookies.txt
```

```bash
docker run -d -v "$PWD/cookies.txt:/app/cookies.txt:ro" ... <image>
```

### Cara 3 — pool cookies di database + rotasi otomatis ⭐ (disarankan produksi)

Cookies dikelola di tabel `ytdlp_cookies` (terenkripsi AES-256-GCM), bisa
banyak akun, dan dirotasi otomatis tanpa redeploy:

```bash
# upload cookies (label unik per akun)
curl -X POST http://localhost:8000/api/admin/ytdlp-cookies \
  -H "Content-Type: application/json" \
  -d '{"label":"akun-1","cookies":"<isi cookies.txt>"}'

# cek semua cookies sekarang
curl -X POST http://localhost:8000/api/admin/ytdlp-cookies/probe-all

# lihat status pool
curl http://localhost:8000/api/admin/ytdlp-cookies
```

| Mekanisme | Otomatis? | Penjelasan |
|-----------|-----------|-----------|
| Refresh token jangka pendek | ✅ | yt-dlp menulis balik cookie jar ke `cookiefile` (`YoutubeDL.save_cookies()`), lalu `sync_back()` mengenkripsi ulang ke DB |
| Rotasi multi-akun | ✅ | `acquire()` memilih cookies aktif yang paling lama tidak dipakai (round-robin) |
| Deteksi kedaluwarsa | ✅ | error `Sign in to confirm`, `cookies are no longer valid`, `HTTP 403`, atau `fail_count >= YTDLP_COOKIE_MAX_FAILURES` → status `expired` |
| Failover | ✅ | cookies `expired` dilewati, download pakai akun berikutnya |
| Login ulang Google | ❌ | bila sesi benar-benar dicabut, cookies baru harus diekspor manual |

Jadwalkan pemeriksaan (cron tiap 6 jam):

```cron
0 */6 * * * cd /app/backend && python ../scripts/check_ytdlp_cookies.py >> /var/log/clipzi-cookies.log 2>&1
```

Script keluar dengan kode `1` bila ada cookies `expired` — cocok untuk alerting.

Endpoint admin cookies:

| Method | Endpoint | Fungsi |
|--------|----------|--------|
| GET | `/api/admin/ytdlp-cookies` | daftar cookies (tanpa isi) |
| POST | `/api/admin/ytdlp-cookies` | upload/timpa cookies |
| POST | `/api/admin/ytdlp-cookies/probe-all` | uji semua + auto-expire |
| POST | `/api/admin/ytdlp-cookies/{id}/probe` | uji satu |
| POST | `/api/admin/ytdlp-cookies/{id}/reactivate` | aktifkan ulang |
| POST | `/api/admin/ytdlp-cookies/{id}/disable` | nonaktifkan |
| GET | `/api/admin/ytdlp-cookies/{id}/content` | lihat plaintext (debug) |
| DELETE | `/api/admin/ytdlp-cookies/{id}` | hapus |

Opsi tambahan:

| Variabel | Fungsi |
|----------|--------|
| `YTDLP_PROXY` | proxy residensial, mis. `http://user:pass@ip:port` |
| `YTDLP_EXTRACTOR_ARGS` | mis. `youtube:player_client=web_safari,android` |

> 🔐 **Cookies = kredensial login.** Pakai akun khusus (bukan akun utama),
> jangan commit `cookies.txt`, dan logout/rotate bila bocor.
> `cookies.txt`, `.cache/`, `downloads/` sudah masuk `.gitignore` & `.dockerignore`.

---

## 🗄 Database & Migrasi

| Item | Nilai |
|------|-------|
| Engine | PostgreSQL 15 (Supabase) |
| Driver | `asyncpg` via SQLAlchemy 2.0 async |
| Jumlah tabel | **31** |
| Pembuatan skema | otomatis saat startup (`Base.metadata.create_all`) |

```python
# app/db/session.py
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, pool_pre_ping=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### Hal penting

1. **`create_all` tidak mengubah tabel yang sudah ada.** Menambah tabel baru →
   otomatis. Mengubah/menghapus kolom → **tidak** diterapkan. Untuk perubahan
   skema, aktifkan Alembic (folder `alembic/versions` masih kosong):

   ```bash
   cd backend
   alembic revision --autogenerate -m "ubah kolom x"
   alembic upgrade head
   ```

2. **`DEBUG=false` di produksi.** `DEBUG=true` membuat `echo=True` → semua SQL
   (termasuk parameter) tercatat di log.

3. **Batas koneksi pooler Supabase.** Engine memakai default pool
   (`pool_size=5`, `max_overflow=10`). Jika menjalankan lebih dari satu proses
   (API + cron + worker), kurangi agar tidak kena `too many connections`:

   ```python
   create_async_engine(url, pool_size=3, max_overflow=2, pool_pre_ping=True)
   ```

4. **Session vs transaction pooler**: pakai port `5432` (session) untuk asyncpg.

### Seed data awal

```bash
cd backend
python ../scripts/seed_pricing.py          # paket harga Free/Standar/Pro/Team
python ../scripts/grant_signup_credits.py  # kredit awal (opsional)
```

---

## ⚡ Redis (Upstash)

Redis dipakai untuk antrean job (ARQ), rate limiting, cache, dan progress task.
Data permanen tetap di PostgreSQL; file video di Cloudflare R2.

1. Buka [console.upstash.com](https://console.upstash.com) → **Create Database**.
2. Tab **Connect** → pilih bagian **redis-cli / TCP** (bukan REST API).
3. Ambil **password** dari string `redis-cli ... -a <PASSWORD>`.
4. Isi `backend/.env`:

```env
REDIS_URL=rediss://default:<PASSWORD_UPSTASH>@<nama-db>.upstash.io:6379
```

| Catatan | Detail |
|---------|--------|
| Wajib `rediss://` | dua huruf `s` = TLS. **Bukan** REST URL (`https://...`) |
| REST Token ≠ password | REST token hanya untuk JS/Node, tidak dipakai backend Python |
| Cek koneksi | `GET /api/health` → `redis: connected` |
| Free tier | ada batas command harian; worker ARQ melakukan polling |
| Redis lokal | `docker compose --profile local-redis up -d` → `REDIS_URL=redis://redis:6379/0` |

---

## 📡 API Reference

Dokumentasi interaktif: **`http://localhost:8000/docs`** · OpenAPI: `/openapi.json` (63 path).

### Publik

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/health` | Kesehatan server + status Redis |
| GET | `/api/formats` | Format & resolusi didukung |
| POST | `/api/auth/register` | Daftar akun (+5 kredit) |
| POST | `/api/auth/login` | Login → access + refresh token |
| POST | `/api/auth/refresh` | Refresh access token |
| POST | `/api/auth/2fa/setup` \| `/verify` | Aktifkan 2FA TOTP |
| GET/PUT | `/api/users/me` | Profil pengguna |
| POST | `/api/tasks` | Buat tugas pemrosesan video |
| GET | `/api/tasks` \| `/api/tasks/{id}` | Daftar / detail tugas |
| DELETE | `/api/tasks/{id}` | Hapus tugas |
| GET | `/api/editing/options` | Daftar fitur editing |
| POST | `/api/editing/validate` | Validasi opsi editing |
| GET | `/api/pricing` | Paket harga |
| POST | `/api/payment/create` | Buat pembayaran Duitku |
| POST | `/api/payment/callback` | Webhook Duitku (publik, URL harus bisa diakses) |
| GET | `/api/credits/history` \| `/balance` | Kredit |
| GET | `/api/analytics/*` | Statistik performa klip |
| CRUD | `/api/api-keys` | API key untuk integrasi |
| CRUD | `/api/webhooks` | Langganan webhook |
| GET | `/api/youtube/auth-url` \| `/status` | OAuth YouTube |
| GET | `/api/youtube/callback` | Callback OAuth (redirect ke frontend) |
| CRUD | `/api/templates` | Template klip |
| POST | `/api/bulk` | Bulk job |
| CRUD | `/api/scheduled-publish` | Jadwal publikasi |
| CRUD | `/api/multi-platform` | Repurpose multi-platform |
| GET | `/api/compliance/*` | GDPR/PDP (export/hapus data) |

### Admin

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| POST | `/api/admin/auth/login` | Login admin |
| GET | `/api/admin/users` | Daftar pengguna |
| POST | `/api/admin/users/{id}/ban` | Blokir pengguna |
| POST | `/api/admin/users/{id}/credits/adjust` | Sesuaikan kredit |
| CRUD | `/api/admin/plans` | Kelola paket |
| GET | `/api/admin/tasks` · `POST /{id}/cancel` | Pantau & batalkan tugas |
| GET | `/api/admin/transactions` | Transaksi |
| GET | `/api/admin/audit` · `/audit/user/{id}/timeline` | Audit trail |
| GET | `/api/admin/security` | Event keamanan |
| GET | `/api/admin/system/health` · `/stats` | Kesehatan & statistik |
| * | `/api/admin/ytdlp-cookies` | Pool cookies yt-dlp (lihat §Cookies) |

> ⚠️ **Keamanan**: sebagian route `/api/admin/*` di codebase ini belum memakai
> guard autentikasi (mengikuti pola awal project). Sebelum produksi, tambahkan
> dependency verifikasi admin ke seluruh router admin, khususnya
> `/api/admin/ytdlp-cookies/{id}/content` yang mengembalikan plaintext cookies.

---

## 💰 Paket Harga

| Paket | Harga/bulan | Kredit | Max Durasi | Concurrent | Fitur Editing | YouTube Upload |
|-------|-------------|--------|------------|------------|---------------|----------------|
| Free | Gratis | 5 (sekali) | 5 menit | 1 | Terbatas | ❌ |
| Standar | Rp 99.000 | 30 | 30 menit | 2 | Sebagian | ✅ |
| Pro | Rp 249.000 | 100 | 60 menit | 5 | Semua | ✅ |
| Team | Rp 499.000 | 300 | 120 menit | 10 | Semua | ✅ |

Seed ke database: `python scripts/seed_pricing.py`

---

## 🔐 Keamanan

| Aspek | Implementasi |
|-------|-------------|
| Password | Argon2id (resistant GPU cracking) |
| Token | JWT HS256 — access 15 menit, refresh 7 hari |
| Data sensitif | AES-256-GCM field-level encryption (`ENCRYPTION_KEY`) |
| Cookies yt-dlp | disimpan terenkripsi di tabel `ytdlp_cookies` |
| 2FA | TOTP (kompatibel Google Authenticator) + backup codes |
| Transport | TLS 1.3 wajib di production |
| Rate limit | Redis, per IP dan per API key |
| Audit | semua aksi admin & user tercatat |
| Secret | `.env` tidak pernah di-commit / masuk image (`.gitignore` + `.dockerignore`) |

Checklist sebelum produksi:

- [ ] `DEBUG=false`
- [ ] `SECRET_KEY` & `ENCRYPTION_KEY` dirotasi (jangan pakai contoh)
- [ ] `CORS_ORIGINS` hanya domain resmi
- [ ] Route `/api/admin/*` diberi guard autentikasi admin
- [ ] `DUITKU_CALLBACK_URL` memakai HTTPS publik
- [ ] Database backup + `alembic` aktif untuk perubahan skema

---

## 📱 Integrasi Android

Contoh pemanggilan API dari aplikasi Android (Kotlin + Retrofit):
```kotlin
// Buat task
val response = apiService.createTask(
    CreateTaskRequest(
        sourceUrl = "https://youtube.com/watch?v=xxx",
        editingOptions = mapOf("auto_zoom_face" to true),
        autoUploadYoutube = true
    )
)

// Polling status
val task = apiService.getTask(response.taskId)
```

Autentikasi memakai header `Authorization: Bearer <access_token>` atau
`X-API-Key: clipzy_<key>` (dibuat dari dashboard).

---

## 🧰 Troubleshooting

### Build & Docker

| Gejala | Solusi |
|--------|--------|
| `failed to connect to the docker API` | Docker Desktop belum jalan |
| Backend container exit saat start | `docker logs <container>`; biasanya env wajib kosong atau `greenlet` hilang (pastikan `sqlalchemy[asyncio]`) |
| `exec format error` | build ulang dengan `--platform linux/amd64` |
| `ModuleNotFoundError: app` | build context harus folder `backend` |

### Aplikasi

| Gejala | Penyebab |
|--------|----------|
| `ModuleNotFoundError: psycopg2` | `DATABASE_URL` belum `postgresql+asyncpg://` |
| `ImportError ... greenlet` | `sqlalchemy` tanpa extra `[asyncio]` |
| Transkripsi 404 | `TRANSCRIPTION_BASE_URL` diisi endpoint lengkap, harus root `/v1` |
| Browser: *blocked by CORS* | `CORS_ORIGINS` tidak cocok dengan origin frontend |
| Frontend memanggil `localhost:8000` | `NEXT_PUBLIC_API_URL` belum di-set saat container dijalankan |
| YouTube: *Sign in to confirm you're not a bot* | butuh cookies yt-dlp (§Cookies) |
| OAuth Google: *redirect_uri_mismatch* | `YOUTUBE_REDIRECT_URI` beda dengan yang didaftarkan, atau memakai `http://IP` (harus HTTPS/domain) |
| `?` di halaman dashboard | cek `NEXT_PUBLIC_API_URL` lalu buka `/runtime-env.js` |

### Editor (VS Code)

| Gejala | Solusi |
|--------|--------|
| Pylance: *Import "fastapi" could not be resolved* | pilih interpreter `backend\.venv` (**Python: Select Interpreter**) — jangan `frontend\.venv` |
| TS: *Expression expected* di `layout.tsx` padahal `tsc` bersih | TS server basi → **TypeScript: Restart TS Server**, atau **File: Revert File** bila buffer dirty |
| `*.css` tidak dikenali | deklarasi ada di `frontend/src/types/assets.d.ts` (harus script-mode, tanpa `export`) |
| Diagnostik aneh setelah buat venv besar | `files.watcherExclude` untuk `.venv`/`node_modules` (sudah di-set) |

Verifikasi cepat dari terminal (sumber kebenaran, bukan panel Problems):

```bash
cd frontend && npx tsc --noEmit          # harus exit 0
cd backend  && .venv\Scripts\python.exe -c "from app.main import app; print(len(app.openapi()['paths']))"
```

---

## 🤝 Kontribusi & Lisensi

1. Fork → buat branch fitur → commit → pull request.
2. Ikuti gaya kode yang ada; jalankan `npx tsc --noEmit` (frontend) dan
   `python -m compileall app` (backend) sebelum push.
3. Jangan pernah commit `.env`, `cookies.txt`, atau file berisi kredensial.

**Lisensi:** MIT








