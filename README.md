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

```bash
docker-compose up -d
```

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
2. Pilih instance GPU min 4GB VRAM
3. Deploy Docker image
4. Set variabel lingkungan dari `.env.example`
5. Dapatkan API Key dan gunakan di aplikasi Android

---

## 🤝 Kontribusi

Silakan buat pull request atau buat issue untuk fitur baru.

---

## 📄 Lisensi

MIT License