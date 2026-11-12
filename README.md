# ClipzyAI

Platform pemotong video panjang menjadi klip pendek siap publikasi (9:16, subtitle karaoke,
watermark, metadata AI). Repo ini berisi backend API, worker GPU di Vast.ai, frontend publik,
dan (menyusul) aplikasi admin terpisah.

## Arsitektur

```
Internet
  |
  +-- proxyai.live ................ Caddy di VPS
  |     |-- /            -> clipzi-web (Next.js 14, frontend publik)
  |     |-- /api/*       -> clipzi-api (FastAPI)
  |     +-- /api/internal/*  (HMAC worker callback)
  |
  +-- admin.proxyai.live ......... Cloudflare Access (2 email) -> clipzi-admin
                                    (aplikasi admin terpisah, template shadcn)

clipzi-api (VPS, FastAPI + PostgreSQL Supabase + Redis + R2)
  +-- membuat task, menyimpan hasil klip ke R2
  +-- InstanceSupervisor: pesan instance GPU Vast.ai, kirim onstart, pantau, hapus

Vast.ai instance (GPU, image sujinwo555/clipzi-backend:worker)
  +-- Whisper large-v3 CUDA (transkripsi lokal, audio tidak keluar instance)
  +-- ffmpeg render + caption ASS karaoke
  +-- AI lewat PROVIDER (diatur admin): rerank momen viral + metadata
  +-- unggah bundle log ke qurl.sh, callback HMAC ke API
```

Tidak ada lagi LLM lokal (llama.cpp/GGUF) di worker: analisis AI memakai provider
OpenAI-compatible apa pun (OpenRouter, OpenAI, Groq, Together, DeepSeek, Mistral, Ollama,
Azure, atau custom).

## Struktur repo

```
backend/        FastAPI, pipeline, services, tests (pytest)
frontend/       Next.js 14 (publik: landing, dashboard user, pricing)
admin/          aplikasi admin (Next.js 16 + shadcn, template Kiranism) - dibangun bertahap
scripts/        build, backup, restore, utilitas Vast
docker-compose.vps.yml   compose yang dipakai produksi di VPS
.github/workflows/docker-backend.yml   build & push image api + worker
```

## Menjalankan lokal

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env                                  # isi DATABASE_URL, SECRET_KEY, R2, dll
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install
npm run dev                                           # http://localhost:3000
```

Test backend:

```bash
cd backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall -q app
```

## Environment (backend/.env)

Hanya variabel yang tidak bisa diatur dari dashboard yang WAJIB di .env.

| Grup | Variabel | Keterangan |
|---|---|---|
| App | `APP_NAME`, `APP_VERSION`, `DEBUG`, `SECRET_KEY`, `FRONTEND_URL`, `CORS_ORIGINS` | `SECRET_KEY` juga menjadi kunci enkripsi API key AI di DB |
| DB | `DATABASE_URL` (`postgresql+asyncpg://...`) | Supabase pooler port 5432 |
| Redis | `REDIS_URL` | rate limit / queue |
| Storage | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `R2_PUBLIC_DOMAIN` | hasil klip & aset branding |
| YouTube | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REDIRECT_URI`, `YOUTUBE_API_KEY` | upload klip |
| Vast | `VAST_API_KEY`, `VAST_WORKER_IMAGE`, `VAST_GPU_FILTER`, `VAST_MAX_ATTEMPTS`, `VAST_BOOT_TIMEOUT`, `VAST_ONESHOT_TIMEOUT` | `VAST_BOOT_TIMEOUT` minimal 900 detik untuk pull image |
| Internal | `CLIPZI_WORKER_TOKEN` | HMAC callback worker |

**Diatur dari dashboard admin (bukan .env):** provider AI, base URL, API key AI, model
metadata/rerank/regenerate, temperature, max tokens, timeout, budget, toggle fitur AI,
nama aplikasi, logo, favicon, warna aksen, watermark.

Nilai AI disimpan terenkripsi (Fernet, kunci dari `SECRET_KEY`) di tabel
`platform_settings` key `ai`, lalu **di-inject ke `os.environ` + objek settings** setiap
kali admin menyimpan dan setiap worker memulai task. Worker membaca dari DB, jadi
perubahan provider berlaku tanpa rebuild image.

## Deploy

1. **Build** - push ke `main`. GitHub Actions membangun dan mendorong
   `sujinwo555/clipzi-backend:api` dan `:worker`. Cek tab Actions sampai hijau.
2. **Update VPS**
   ```bash
   ssh root@<vps>
   cd /opt/clipzi/app
   docker compose -f docker-compose.vps.yml pull backend
   docker compose -f docker-compose.vps.yml up -d backend
   curl -s -o /dev/null -w '%{http_code}' https://proxyai.live/api/health
   ```
3. **Frontend** (bila berubah): `docker compose -f docker-compose.vps.yml up -d --build frontend`
4. **Ruang disk**: `docker builder prune -af && docker image prune -af`

Workflow tidak boleh dijalankan saat ada task berjalan (restart API di tengah task
membuat callback hilang).


## Dashboard admin

Semua pengaturan platform ada di `admin.proxyai.live` (dilindungi Cloudflare Access):

- **Overview** - revenue, user baru, task sukses/gagal, kredit, biaya Vast.
- **Tasks** - daftar/filter task, detail klip, `log_tail`, `LOG_URL`, retry/cancel.
- **Users** - cari user, ubah plan, adjust kredit, ban/unban, export.
- **Workers** - instance Vast.ai aktif + riwayat percobaan, biaya, destroy manual.
- **Transactions** - riwayat pembayaran, refund, export.
- **Audit** - semua aksi admin (before/after).
- **Settings > AI** - provider, base URL, API key, 3 model, temperature, max tokens,
  timeout, budget, toggle rerank/metadata, tombol **Test Connection**.
- **Settings > Branding** - nama aplikasi, tagline, logo, favicon, og image, warna aksen.
- **Settings > Watermark** - teks/logo watermark per plan (sudah ada).

Endpoint admin:

```
GET/PUT  /api/admin/settings/ai            setelan AI (key selalu termask)
POST     /api/admin/settings/ai/test       uji kredensial provider + latency
GET/PUT  /api/admin/settings/branding      branding platform
POST     /api/admin/settings/branding/upload?kind=logo|favicon|og
GET      /api/branding                     (publik) dipakai layout & navbar
```

## Alur task

1. User membuat task di dashboard -> `POST /api/tasks`.
2. `InstanceSupervisor` memilih offer Vast.ai (GPU >= 12 GB, disk >= 40 GB, network
   tinggi), membuat instance, mengirim `onstart` berisi `CLIPZI_TASK_ID`.
3. Worker: unduh video -> Whisper GPU -> `clip_planner` (heuristik + rerank provider)
   -> metadata provider -> render ffmpeg + caption ASS -> unggah ke R2.
4. Worker mengunggah bundle log (`worker.log`, `env.txt`, SRT/ASS) ke qurl.sh lalu
   callback HMAC ke API (`ai_info`, `ai_failed`, `logs`, `logs_failed`).
5. Task selesai/gagal -> instance dihapus (dengan guard: tidak menghapus instance
   milik task lain dan tidak menghapus saat task masih berjalan).

Bila provider AI gagal atau belum diatur, task tetap selesai: rerank memakai skor
heuristik dan metadata memakai `build_heuristic_metadata()` dari transkrip. Tidak ada
fallback CPU diam-diam untuk LLM (LLM lokal sudah tidak dipakai).

## Observability

- `GET /api/admin/workers/instances` - instance + `log_tail` (note `ai_info`,
  `ai_failed`, `rerank_skipped`, `logs`, `logs_failed`).
- `LOG_URL=https://qurl.sh/...` berisi log lengkap per task + instance.
- Log worker juga ditulis ke `/tmp/clipzi-worker.log` di instance.

## Keamanan endpoint

1. Admin berada di subdomain terpisah (`admin.proxyai.live`) dan dilindungi
   **Cloudflare Access** (policy: hanya email yang diizinkan, session 6 jam).
2. Di domain publik, `/api/admin/*` dibalas **404** oleh Caddy (bukan 401) supaya
   keberadaan endpoint tidak terkonfirmasi.
3. Dokumentasi FastAPI dimatikan di produksi (`docs_url`, `redoc_url`, `openapi_url`).
4. Callback worker wajib HMAC (`CLIPZI_WORKER_TOKEN`), tidak didaftarkan di router publik.
5. Login admin: lockout 5 gagal, cookie HttpOnly + SameSite=Strict, dukungan TOTP.

## Backup & Restore (satu perintah, satu file)

Backup **semua** komponen (database, seluruh source semua branch, seluruh file konfigurasi
termasuk `.env`, daftar image, manifest + checksum) ke satu arsip:

```bash
# di VPS
cd /opt/clipzi/app
bash scripts/backup-all.sh
# -> /opt/clipzi/app/backups/clipzi-YYYYmmdd-HHMMSS.tar.gz
```

Dari Windows (backup di VPS lalu otomatis diunduh ke PC):

```powershell
.\scripts\backup-all.ps1
# opsional: .\scripts\backup-all.ps1 -SkipDb   atau   -OutDir D:\backup
```

Isi arsip:

```
db/clipzi.dump     pg_dump -Fc (data + skema)
db/schema.sql      skema saja
repo.bundle        git bundle --all  (backend + frontend, semua branch/commit)
config/            backend/.env, .env, docker-compose*.yml, Caddyfile*, deployments, TODO
images.txt         image + digest yang dipakai
manifest.txt       waktu, host, commit, daftar file
SHA256SUMS         checksum (diverifikasi saat restore)
```

Restore (VPS baru atau setelah bencana):

```bash
bash scripts/restore-all.sh /root/backup/clipzi-20260101-120000.tar.gz
# opsi: --db-only | --config-only | --app-dir /opt/clipzi/app
```

Restore melakukan: verifikasi checksum -> kembalikan config (file lama di-`.bak`) ->
clone source dari `repo.bundle` bila repo belum ada -> `pg_restore --clean --if-exists` ->
`docker compose up -d` -> tunggu `https://proxyai.live/api/health` = 200.

## Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| `[ai_failed] AI belum aktif` | Isi provider + API key di Settings > AI, tekan Test Connection |
| `ai_failed: 401` | API key salah/kadaluarsa, atau base URL bukan endpoint OpenAI-compatible |
| Task lambat tanpa alasan | Cek `log_tail`; bila rerank dilewati, provider timeout - naikkan `timeout_seconds` |
| Instance gagal boot | `registry-1.docker.io` timeout: naikkan `VAST_BOOT_TIMEOUT` (900+), ulangi task |
| `Sign in to confirm you're not a bot` | YouTube minta cookies: unggah cookies di admin (ytdlp cookies) |
| Disk VPS penuh | `docker builder prune -af && docker image prune -af` |
| Instance tertinggal | `GET /api/admin/workers/instances`, destroy manual, atau tunggu supervisor |

## Testing

```bash
cd backend
.venv\Scripts\python.exe -m pytest -q          # unit + regression
.venv\Scripts\python.exe -m compileall -q app
```

Test penting: `test_ai_config.py` (enkripsi + injeksi env), `test_provider_llm.py`
(deadline/JSON/error provider), `test_branding.py`, `test_clip_planner.py`,
`test_caption_ass.py`, `test_instance_supervisor.py`, `test_supervisor_guard.py`,
`test_log_bundle*.py`.

## Admin subdomain & Cloudflare Access

`admin.proxyai.live` dilayani Caddy (`deploy/Caddyfile`) dan dilindungi dua lapis:

1. **basic_auth** (cadangan) - user `clipzy`, hash di env `ADMIN_BASIC_AUTH`
   pada service `caddy` di `docker-compose.vps.yml`. Ganti dengan:
   ```bash
   docker run --rm caddy:2-alpine caddy hash-password --plaintext 'PASSWORD-BARU'
   ```
   lalu update `ADMIN_BASIC_AUTH` (escape `$` menjadi `$$` di compose) dan
   `docker compose up -d caddy`.
2. **Cloudflare Access (Zero Trust)** - buat aplikasi self-hosted untuk
   `admin.proxyai.live` dengan policy `allow` hanya email:
   `sujinwo555@gmail.com` dan `admin@proxyai.live`, session 6 jam. Setelah aktif,
   basic_auth boleh dihapus dari Caddy.

Di domain publik, `/api/admin/*` dibalas **404** (bukan 401) supaya endpoint tidak
terkonfirmasi. Dokumentasi API juga dibalas 404.
