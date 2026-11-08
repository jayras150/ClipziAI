# Clipzi AI

Ubah Video Panjang → Shorts Viral Dalam 1 Klik

**Versi:** 1.0 — Full Stack + AI + Deployment + Android API

---

## 📋 Fitur Utama

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
- YouTube Upload (OAuth2)
- Scheduled Publish (YouTube, TikTok, Instagram, Facebook)
- Multi-Platform Repurpose (satu video → banyak platform)
- Bulk Processing (satu video panjang → banyak klip)

### Akun & Pembayaran
- Login: Email atau Sosial Media (Google, X/Twitter, Facebook)
- 2FA (TOTP + Kode Cadangan)
- Paket: Free, Standar, Pro, Team
- Sistem Kredit (Try for Free: 5 kredit gratis)
- Pembayaran: Duitku Payment Gateway
- Invoice Otomatis (PDF)

### Keamanan & Admin
- Admin Dashboard dengan RBAC (Super Admin, Admin, Moderator)
- Audit Trail Lengkap (setiap aksi pengguna dicatat)
- Enkripsi AES-256-GCM untuk data sensitif
- Password Hashing: Argon2id
- Rate Limiting per API Key
- Content Moderation & Copyright Check
- GDPR/PDP Compliance (Export/Hapus Data)

---

## 🚀 Quick Start

### 1. Clone & Setup Backend

```bash
cd backend
cp .env.example .env
# Edit .env dengan kredensial Anda

# Install dependencies
pip install -r requirements.txt

# Setup database
python scripts/seed_pricing.py

# Run server
uvicorn app.main:app --reload --port 8000
```

### 2. Setup Frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Deploy dengan Docker

Tersedia dua image terpisah: **backend** (FastAPI) dan **frontend** (Next.js).

#### a. Jalankan dari source (docker compose)

```bash
cp backend/.env.example backend/.env   # lalu isi kredensial
docker compose up -d --build
```

Backend di `http://localhost:8000`, frontend di `http://localhost:3000`.

#### b. Build & push ke Docker Hub (image portable)

```powershell
# Windows
./scripts/build-and-push.ps1 -DockerHubUser <username-dockerhub> -Tag 1.0.0
```

```bash
# Linux / macOS / instance Vast.ai
./scripts/build-and-push.sh <username-dockerhub> 1.0.0
```

Perintah di atas menghasilkan:

| Image | Keterangan |
|-------|-----------|
| `<user>/clipzi-backend:<tag>` | FastAPI + ffmpeg + yt-dlp + faster-whisper, non-root user, healthcheck `/api/health` |
| `<user>/clipzi-frontend:<tag>` | Next.js standalone (Node 20 Alpine), non-root user |

#### c. Menjalankan image di server mana pun

```bash
# Backend — semua rahasia dibaca dari file .env (tidak ikut masuk image)
docker run -d --name clipzi-api \
  -p 8000:8000 \
  --env-file backend/.env \
  <user>/clipzi-backend:1.0.0

# Frontend — NEXT_PUBLIC_API_URL bisa diganti kapan saja tanpa rebuild
docker run -d --name clipzi-web \
  -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://IP_PUBLIK:8000 \
  <user>/clipzi-frontend:1.0.0
```

Atau lewat compose untuk image hasil push:

```bash
export DOCKERHUB_USER=<username-dockerhub>
export TAG=1.0.0
export NEXT_PUBLIC_API_URL=http://IP_PUBLIK:8000
docker compose -f docker-compose.prod.yml up -d
```

> **Kenapa `NEXT_PUBLIC_API_URL` bisa runtime?**
> `frontend/docker-entrypoint.sh` menulis `/app/public/runtime-env.js` setiap
> container start. Nilainya dibaca lewat `window.__ENV__` (lihat
> `frontend/src/lib/env.ts`), sehingga **satu image** bisa dipakai di laptop,
> Vast.ai, atau VPS tanpa rebuild.

---

## 🤖 Konfigurasi Provider AI

Semua layanan LLM Clipzi AI—**viral scoring**, pembuatan **judul/deskripsi/tag**, dan fitur AI terkait—memakai satu konfigurasi provider di `backend/.env`. Pilih provider OpenAI-compatible apa pun tanpa mengubah source code.

```env
# Provider bawaan yang didukung: openai, groq, openrouter, together,
# deepseek, mistral, azure, ollama, atau custom.
AI_PROVIDER=groq
AI_API_KEY=gsk_your-key
AI_MODEL=llama-3.1-8b-instant

# AI_BASE_URL boleh dikosongkan untuk provider bawaan.
# Untuk endpoint kompatibel OpenAI milik sendiri, isi URL endpoint /v1:
AI_BASE_URL=
```

Contoh Ollama lokal (tanpa API key):

```env
AI_PROVIDER=ollama
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3.1
AI_API_KEY=
```

Untuk provider khusus, gunakan `AI_PROVIDER=custom`, lalu isi `AI_BASE_URL`, `AI_API_KEY` bila diperlukan, dan `AI_MODEL`. `OPENAI_API_KEY` tetap didukung hanya sebagai fallback kompatibilitas lama apabila `AI_API_KEY` kosong.

### Konfigurasi Provider Transkripsi / Whisper

Transkripsi dipisahkan dari provider LLM. Gunakan `TRANSCRIPTION_PROVIDER=local` untuk `faster-whisper` lokal, atau gunakan provider mana pun yang kompatibel dengan endpoint OpenAI `/audio/transcriptions`.

```env
# faster-whisper lokal (default; model diunduh/dijalankan pada server)
TRANSCRIPTION_PROVIDER=local
WHISPER_MODEL=small
```

```env
# Provider cloud OpenAI-compatible, misalnya Groq
TRANSCRIPTION_PROVIDER=groq
TRANSCRIPTION_API_KEY=gsk_your-key
TRANSCRIPTION_BASE_URL=https://api.groq.com/openai/v1
TRANSCRIPTION_MODEL=whisper-large-v3-turbo
```

Untuk provider custom, gunakan `TRANSCRIPTION_PROVIDER=custom`, isi `TRANSCRIPTION_BASE_URL` dengan endpoint `/v1`, lalu isi `TRANSCRIPTION_API_KEY` dan `TRANSCRIPTION_MODEL`. Jika `TRANSCRIPTION_API_KEY` kosong, backend melakukan fallback kompatibilitas ke `AI_API_KEY`, lalu `OPENAI_API_KEY`. Provider cloud harus mendukung respons `verbose_json` dan timestamp segmen; timestamp per kata digunakan jika provider mendukungnya.

---

## 🍪 Cookies yt-dlp (OPSIONAL)

yt-dlp **tidak** memakai cookies secara otomatis. Tanpa cookies, download tetap
jalan untuk **video publik dari IP residensial**, tetapi akan gagal di IP
datacenter (Vast.ai / VPS / cloud) dengan pesan:

```
Sign in to confirm you're not a bot
```

Isi cookies **hanya jika** menemui error tersebut, atau butuh video
age-restricted / private / member-only. Ada dua cara:

#### Cara 1 — base64 (paling praktis untuk Docker)

```bash
# 1. Login YouTube di browser, pasang ekstensi "Get cookies.txt LOCALLY"
# 2. Export cookies -> simpan cookies.txt
# 3. Encode jadi base64
python scripts/encode_cookies.py cookies.txt
```

Tempel hasilnya ke `backend/.env`:

```env
YTDLP_COOKIES_BASE64=H4sIAAAA...   # satu baris panjang
```

Backend akan men-decode-nya ke `.cache/ytdlp_cookies.txt` saat pertama kali
dipakai (tidak ikut masuk image).

#### Cara 2 — file langsung

```env
YTDLP_COOKIES_FILE=/app/cookies.txt
```

Jalankan container dengan file di-mount:

```bash
docker run -d --name clipzi-api -p 8000:8000 \
  -v "$PWD/cookies.txt:/app/cookies.txt:ro" \
  --env-file backend/.env <user>/clipzi-backend:1.0.0
```

#### Opsi tambahan bila cookies masih kurang

| Variabel | Fungsi |
|----------|--------|
| `YTDLP_PROXY` | Proxy residensial, mis. `http://user:pass@ip:port` |
| `YTDLP_EXTRACTOR_ARGS` | Mis. `youtube:player_client=web_safari,android` |

> ⚠️ **Cookies = kredensial login.** Gunakan akun khusus (bukan akun utama),
> jangan commit `cookies.txt`, dan logout/rotate bila file bocor.
> `cookies.txt`, `.cache/`, dan `downloads/` sudah masuk `.gitignore` dan
> `.dockerignore`.

### 🔄 Rotasi otomatis (multiple akun, tanpa redeploy)

Cara statis di atas akan mati saat sesi Google dicabut. Untuk produksi, cookies
dikelola lewat database (tabel `ytdlp_cookies`, terenkripsi AES-256-GCM):

```bash
# 1. Upload cookies (boleh banyak akun, label unik)
curl -X POST http://localhost:8000/api/admin/ytdlp-cookies \
  -H "Content-Type: application/json" \
  -d '{"label":"akun-1","cookies":"<isi cookies.txt>"}'

# 2. Cek semua cookies sekarang
curl -X POST http://localhost:8000/api/admin/ytdlp-cookies/probe-all

# 3. Lihat status pool
curl http://localhost:8000/api/admin/ytdlp-cookies
```

**Apa yang otomatis:**

| Mekanisme | Penjelasan |
|-----------|-----------|
| Rotasi multi-akun | `acquire()` memilih cookies aktif yang paling lama tidak dipakai (round-robin) — beban tersebar, risiko per akun turun |
| Refresh token jangka pendek | yt-dlp menulis balik cookie jar ke `cookiefile` (`YoutubeDL.save_cookies()`), lalu `sync_back()` mengenkripsi ulang ke DB → token seperti `__Secure-1PSIDTS` tetap segar |
| Deteksi kedaluwarsa | Teks error diuji terhadap penanda seperti `Sign in to confirm`, `cookies are no longer valid`, `HTTP 403`; atau `fail_count >= YTDLP_COOKIE_MAX_FAILURES` → status `expired` |
| Failover | Cookies `expired` otomatis dilewati, download memakai akun berikutnya |

**Apa yang tetap manual:** bila sesi Google benar-benar mati (dicabut / logout
massal / verifikasi keamanan), tidak ada tool yang bisa menghidupkannya tanpa
login ulang — ekspor cookies baru dan upload lagi ke endpoint di atas.

**Jadwalkan pemeriksaan (cron tiap 6 jam):**

```cron
0 */6 * * * cd /app/backend && python ../scripts/check_ytdlp_cookies.py >> /var/log/clipzi-cookies.log 2>&1
```

Script keluar dengan kode `1` bila ada cookies yang jadi `expired` — bisa dipakai
untuk alerting (email/webhook).

> 💡 Boleh isi beberapa akun (mis. 3–5). Dengan rotasi, satu akun yang kena
> rate-limit tidak menghentikan seluruh pipeline.

---

## ⚡ Konfigurasi Redis (Upstash)

Redis dipakai untuk antrean job (ARQ), rate limiting, cache, dan progress task. Data permanen tetap di PostgreSQL/Supabase, dan file video di Cloudflare R2.

1. Buka [console.upstash.com](https://console.upstash.com) → **Create Database** (Redis) → pilih region terdekat.
2. Di tab **Details → Connect**, salin string TCP dan pastikan awalannya `rediss://`.
3. Isi `backend/.env`:

```env
REDIS_URL=rediss://default:<PASSWORD_UPSTASH>@<nama-db>.upstash.io:6379
```

Catatan penting:
- Gunakan **TCP URL (`rediss://`)**, bukan REST URL/REST Token (`https://...`).
- Free tier Upstash memiliki batas command harian; worker ARQ melakukan polling sehingga untuk beban produksi pilih paket yang sesuai.
- Cek koneksi lewat `GET /api/health` (`redis: connected`).
- Redis lokal masih tersedia opsional: `docker compose --profile local-redis up -d`, lalu `REDIS_URL=redis://localhost:6379/0`.

---

## 📖 Dokumentasi Lengkap

### Backend API

#### Endpoint Publik
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/health` | Cek kesehatan server |
| GET | `/api/formats` | Format dan resolusi yang didukung |
| POST | `/api/auth/register` | Daftar akun baru |
| POST | `/api/auth/login` | Masuk |
| POST | `/api/auth/refresh` | Refresh token |
| POST | `/api/tasks` | Buat tugas pemrosesan video |
| GET | `/api/tasks/{id}` | Cek status tugas |
| GET | `/api/tasks` | Daftar tugas pengguna |
| DELETE | `/api/tasks/{id}` | Hapus tugas |
| GET | `/api/editing/options` | Daftar fitur editing yang tersedia |
| POST | `/api/editing/validate` | Validasi opsi editing |
| GET | `/api/pricing` | Daftar paket harga |
| POST | `/api/payment/create` | Buat pembayaran Duitku |
| POST | `/api/payment/callback` | Callback Duitku |
| GET | `/api/credits/history` | Riwayat kredit |

#### Endpoint Admin
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| POST | `/api/admin/auth/login` | Masuk admin |
| GET | `/api/admin/users` | Daftar semua pengguna |
| POST | `/api/admin/users/{id}/ban` | Blokir pengguna |
| POST | `/api/admin/users/{id}/credits/adjust` | Sesuaikan kredit |
| GET | `/api/admin/plans` | Kelola paket harga |
| GET | `/api/admin/tasks` | Pantau semua tugas |
| POST | `/api/admin/tasks/{id}/cancel` | Batalkan tugas |
| GET | `/api/admin/audit` | Lihat audit log |
| GET | `/api/admin/audit/user/{id}/timeline` | Timeline aktivitas pengguna |
| GET | `/api/admin/security` | Lihat event keamanan |
| GET | `/api/admin/system/health` | Kesehatan sistem |

---

## 💰 Paket Harga

| Paket | Harga/bulan | Kredit | Max Durasi | Concurrent | Fitur Editing | YouTube Upload |
|-------|-------------|--------|------------|------------|---------------|----------------|
| Free | Gratis | 5 (once) | 5 menit | 1 | Terbatas | ❌ |
| Standar | Rp 99.000 | 30 | 30 menit | 2 | Sebagian | ✅ |
| Pro | Rp 249.000 | 100 | 60 menit | 5 | Semua | ✅ |
| Team | Rp 499.000 | 300 | 120 menit | 10 | Semua | ✅ |

---

## 🔐 Keamanan

- **Password:** Argon2id (resistant GPU cracking)
- **Token:** JWT HS256 (access 15 menit, refresh 7 hari)
- **Data Sensitif:** AES-256-GCM field-level encryption
- **2FA:** TOTP (Google Authenticator kompatibel) + backup codes
- **Transport:** TLS 1.3 (wajib production)
- **Rate Limit:** Redis-based per IP dan per user
- **Audit:** Semua aksi admin dan pengguna dicatat

---

## 📱 Integrasi Android (Kotlin/Retrofit)

Contoh pemanggilan API dari Android:

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

Lihat `docs/android-client.md` untuk contoh lengkap.

---

## 📦 Deployment ke Vast.ai

1. Buat akun di [Vast.ai](https://vast.ai)
2. Build & push image lebih dulu: `./scripts/build-and-push.ps1 -DockerHubUser <user>`
3. Sewa instance (GPU min 4GB VRAM; CPU-only cukup untuk API + transkripsi cloud),
   lalu pilih/tempel image `<user>/clipzi-backend:<tag>` pada kolom image
4. Tambahkan port `8000` (API) dan `3000` (frontend) di pengaturan instance
5. Isi environment lewat `--env-file` atau variabel lingkungan Vast.ai
   (lihat `backend/.env.example`)
6. Frontend dijalankan dengan
   `-e NEXT_PUBLIC_API_URL=http://<IP_PUBLIK_INSTANCE>:8000`
7. Ambil API Key dari dashboard dan gunakan di aplikasi Android

> Catatan storage: file video sebaiknya langsung diarahkan ke Cloudflare R2
> (`R2_*`), karena disk instance Vast.ai bersifat sementara.

---

## 🤝 Kontribusi

Silakan buat pull request atau buat issue untuk fitur baru.

---

## 📄 Lisensi

MIT License