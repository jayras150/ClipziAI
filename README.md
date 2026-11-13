# ClipzyAI

Platform pemotong video panjang menjadi klip pendek siap publikasi (9:16, subtitle karaoke,
watermark, metadata AI). Repo ini berisi backend API, worker GPU di Vast.ai, frontend publik,
dan aplikasi admin terpisah.

## Peta cepat (mau ubah apa, buka bagian mana)

| Aku mau… | Bagian |
|---|---|
| Ganti domain / pindah hostname (1 klik) | [Setelan ekosistem & ganti domain](#setelan-ekosistem--ganti-domain-1-klik) |
| Ganti provider AI / muat daftar model | [AI provider & daftar model](#ai-provider--daftar-model) |
| Update cookies YouTube (base64 / Netscape) | [Cookies YouTube](#cookies-youtube-base64--netscape) |
| Ban user, ubah plan, lihat log user | [Dashboard admin](#dashboard-admin) › Users |
| Lihat biaya GPU & log worker | [Dashboard admin](#dashboard-admin) › Workers |
| Masalah login admin / "Something went wrong" | [Sesi & logout](#sesi--logout) + [Troubleshooting](#troubleshooting) |
| API mati, AI test gagal, Vast hang | [Troubleshooting](#troubleshooting) |
| Pindah VPS / setup dari nol | [Pindah VPS / setup dari nol](#pindah-vps--setup-dari-nol-runbook-lengkap) |
| Backup & restore | [Backup & Restore](#backup--restore-satu-perintah-satu-file) |

## Changelog penting

Setiap perubahan besar dicatat di sini (tanggal · area · ringkasan · cara verifikasi).

| Tanggal | Area | Perubahan | Verifikasi |
|---|---|---|---|
| 12 Nov 2026 | Firewall | `DOCKER-USER` kini hanya membatasi trafik **masuk** (`-i $WAN`). Sebelumnya ikut memblokir **outbound HTTPS container** → AI test `HTTP 000`, startup Vast hang, API 502. | `/usr/local/sbin/clipzi-cf-firewall.sh --check` → `example.com 200`, `openrouter 200` |
| 12 Nov 2026 | Sesi admin | Refresh token 30 hari + sliding refresh di middleware; cookie access 12 jam. Tidak ada lagi 401 tiap 60 menit. | Buka dashboard > 1 jam tetap tampil |
| 12 Nov 2026 | Logout | Tombol logout di sidebar, header, dan command palette + `logout-all` (cabut semua sesi via tabel `auth_revocations`). | `POST /api/admin/auth/logout` lalu akses endpoint → 401 |
| 12 Nov 2026 | Overview | Template demo dihapus; 100% data nyata (KPI, grafik task/klip/signup, status task, top user, health). | Angka cocok dengan `GET /api/admin/system/stats` |
| 12 Nov 2026 | Users | Daftar + filter/pagination, halaman detail (plan, kredit, tasks, transaksi, log), ban/suspend/aktifkan, adjust kredit, set plan, reset password, paksa logout. Body JSON (fix 422). | `/dashboard/users` → klik nama |
| 12 Nov 2026 | Tasks/Transaksi/Audit | Filter + pagination + detail task + cancel/retry; ringkasan pendapatan; audit bisa difilter. | `/dashboard/tasks`, `/dashboard/transactions`, `/dashboard/audit` |
| 12 Nov 2026 | AI | Provider bertambah (18, semua punya base URL bawaan) + `GET /api/admin/settings/ai/providers` + `POST /api/admin/settings/ai/models`; dropdown provider & model dengan kolom pencarian. | Settings › AI › "Muat daftar model" |
| 12 Nov 2026 | Domain | Setelan `platform` di DB, tombol **Terapkan domain** 1 klik, agent `clipzi-domain-sync` (systemd timer 30 s) menulis `.env` + reload Caddy + opsional DNS Cloudflare. | Settings › Platform › Terapkan domain |
| 12 Nov 2026 | Cookies YouTube | Simpan cookies dari **base64** atau Netscape, validasi, uji (probe), aktif/nonaktif, hapus, ekspor base64. Tetap terenkripsi AES-256-GCM. | Settings › YouTube Cookies |
| 12 Nov 2026 | Landing | Menu FEATURES/HOW IT WORKS/DEMO benar-benar center (grid `1fr auto 1fr`). | Buka `https://domain` di desktop |
| 13 Nov 2026 | Indikator proses | Spinner animasi Clipzy (`orbit`/`ring`/`dots`) dipakai admin & frontend. Tombol submit otomatis spinner (`useFormStatus`), `loading.tsx` per rute, banner shimmer saat task queued/processing. | Klik aksi apa pun di admin → spinner; buka `/dashboard` saat memuat |
| 13 Nov 2026 | Worker yt-dlp | Format ladder `bv*…/bv*+ba/b/b*` + client ladder (default→web→android/ios→tv_embedded) + retry tanpa cookies + dump format saat gagal + cek `has_audio` (retry audio wajib). `yt-dlp>=2026.10.26`. | Task YouTube dari dashboard selesai; log worker memuat daftar format bila gagal |
| 13 Nov 2026 | Branding | `BrandingProvider` + `BrandLogo`: logo/nama/favicon berlaku di **semua** halaman (landing, login, register, dashboard, footer, navbar), accent color live, favicon/OG cache-bust, kartu pratinjau logo/favicon/OG dengan dimensi & ukuran. | Ganti logo di admin → semua halaman + tab browser berubah |
| 13 Nov 2026 | Proxy YouTube | Upload banyak file .txt → engine normalisasi (`proxy_parser`) → tombol **START FILTER ACTIVE PROXY** menguji semua proxy, membuang yang mati, dan membuat satu `active.txt` yang otomatis dipakai worker (rotasi). Layer download: cookies → tanpa cookies → proxy. | Settings › YouTube Cookies › Proxy |
| 13 Nov 2026 | Storage multi-provider | Registry `storage` (R2, Backblaze B2, S3, Wasabi, Spaces, Supabase, GCS, MinIO, dll): primary + mirror, kredensial terenkripsi, uji koneksi, dan **Sync** objek ke mirror. Semua upload memakai satu pintu `get_storage()`. | Settings › Storage |
| 13 Nov 2026 | PO token | Plugin `bgutil-ytdlp-pot-provider` + server Node dibaking ke image worker; `pipeline_onstart.sh` menjalankan provider di `127.0.0.1:4416`. Melengkapi cookies saat YouTube membatasi format. | Log worker: `bgutil PO token provider siap` |
| 13 Nov 2026 | Monitoring VPS | Agent host `clipzi-host-metrics` (systemd, 5 s) → `POST /api/internal/host-metrics`; endpoint `GET /api/admin/system/host`; System tab menampilkan CPU/RAM/disk/jaringan/container realtime tiap 3 s + grafik 10 menit. | System → kartu live bergerak, badge `live` |

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

Semua pengaturan platform ada di `admin.<domain>` (dilindungi Cloudflare Access).

- **Overview** - KPI nyata: user, task (selesai/gagal/error rate), klip, pendapatan paid,
  kredit hari ini/7 hari, rata-rata durasi task, worker aktif, status AI + latensi DB;
  grafik task & klip per hari (30 hari), pendaftar baru, distribusi status, top user.
- **Tasks** - filter status/pencarian, pagination, halaman detail task (klip, error,
  opsi editing), tombol **Batalkan** dan **Ulangi**.
- **Users** - pencarian + filter status/plan, pagination, dan halaman detail per user
  (klik nama): ringkasan plan/kredit/task/klip/belanja, **edit nama & email**,
  **set plan**, **adjust kredit**, **blokir/buka blokir/tangguhkan/aktifkan**,
  **reset password** (password sementara tampil sekali), **paksa logout**,
  daftar task, riwayat kredit, transaksi pembayaran, dan **log aktivitas**.
- **Workers** - instance Vast.ai aktif + riwayat percobaan, biaya, `LOG_URL`, destroy.
- **Transactions** - total pembayaran sukses, filter status/pencarian, pagination.
- **Audit** - filter pelaku/aksi/pencarian, pagination.
- **Alerts** - task gagal + instance gagal yang perlu perhatian.
- **Settings > AI** - dropdown provider (18 provider, semua punya base URL bawaan),
  API key, **daftar model otomatis dengan kolom pencarian**, 3 slot model, temperature,
  max tokens, timeout, budget, toggle rerank/metadata, **Test Connection**.
- **Settings > Platform** - domain publik/admin, email dukungan, timezone, Google Client ID,
  pendaftaran, mode maintenance, dan **ganti domain 1 klik**.
- **Settings > YouTube Cookies** - simpan cookies dari base64 atau Netscape, validasi,
  uji (probe), aktif/nonaktif, hapus, ekspor base64.
- **Settings > Branding** - nama aplikasi, tagline, logo, favicon, og image, warna aksen.

Endpoint admin (semua butuh JWT + email di `ADMIN_EMAILS`):

```
GET      /api/admin/auth/me | /session
POST     /api/admin/auth/logout | /logout-all

GET      /api/admin/users/?q&status&plan&page&page_size
GET      /api/admin/users/{id}                  detail + profil + statistik
PATCH    /api/admin/users/{id}                  nama/email/aktif/verified
POST     /api/admin/users/{id}/ban | /unban | /suspend | /activate
POST     /api/admin/users/{id}/credits/adjust   body {amount, description}
POST     /api/admin/users/{id}/plan             body {plan, expires_at?, reset_credits?}
POST     /api/admin/users/{id}/reset-password | /force-logout
GET      /api/admin/users/{id}/tasks | /credit-transactions | /transactions | /timeline

GET      /api/admin/tasks/?status&q&page    GET /api/admin/tasks/{id}
POST     /api/admin/tasks/{id}/cancel | /retry
GET      /api/admin/transactions/?status&q&page   GET /api/admin/transactions/summary
GET      /api/admin/audit/?actor_type&action&q&page   GET /api/admin/audit/detail/{id}

GET/PUT  /api/admin/settings/ai            setelan AI (key selalu termask)
GET      /api/admin/settings/ai/providers  metadata provider + base URL bawaan
POST     /api/admin/settings/ai/models     daftar model dari provider (cache 5 menit)
POST     /api/admin/settings/ai/test       uji kredensial provider + latency

GET/PUT  /api/admin/settings/platform      setelan ekosistem (domain, dukungan, maintenance)
POST     /api/admin/settings/platform/apply-domain   permintaan ganti domain (1 klik)
GET      /api/admin/settings/platform/domain-status  progres pending/applied/failed
POST     /api/admin/settings/platform/domain-cancel   batalkan permintaan

GET/POST /api/admin/ytdlp-cookies          daftar/tambah cookies (Netscape atau base64)
POST     /api/admin/ytdlp-cookies/validate | /import-base64 | /probe-all
GET      /api/admin/ytdlp-cookies/settings | PUT (mode db/base64 + simpan base64)
GET      /api/admin/ytdlp-cookies/{id}/base64   ekspor untuk env worker
POST     /api/admin/ytdlp-cookies/{id}/probe | /reactivate | /disable   DELETE /{id}

GET      /api/admin/system/stats | /metrics?days=30 | /health

GET/PUT  /api/admin/settings/branding      POST /branding/upload?kind=logo|favicon|og
GET      /api/branding                     (publik) dipakai layout & navbar
GET      /api/pricing/*                    plan publik
```

## Indikator proses (spinner)

Semua proses yang butuh waktu punya indikator visual yang konsisten — tidak ada lagi
tombol "diam" atau halaman kosong saat menunggu API.

**Komponen**

| Lokasi | Komponen | Varian |
|---|---|---|
| Admin | `admin/src/components/ui/clipzy-spinner.tsx` → `ClipzySpinner`, `InlineSpinner`, `ProcessingBar`, `OverlayLoader` | `orbit` (default), `ring` (di tombol), `dots` (teks) |
| Frontend | `frontend/src/components/ClipzySpinner.tsx` → `ClipzySpinner`, `InlineSpinner`, `ProcessingBar` | idem |

Animasi murni CSS (`cz-orbit-spin`, `cz-ring-sweep`, `cz-orbit-pulse`, `cz-dot-bounce`,
`cz-shimmer`) di `admin/src/styles/globals.css` dan `frontend/src/app/theme.css`.
Semua `transform`/`opacity` (60 fps), dan otomatis melambat bila pengguna mengaktifkan
`prefers-reduced-motion`.

**Tombol submit otomatis**

`admin/src/components/ui/submit-button.tsx` memakai `useFormStatus()`: cukup ganti
`<Button type='submit'>` menjadi `<SubmitButton>` di dalam `<form action={...}>`, maka
tombol langsung menampilkan spinner + disabled selama server action berjalan. Dipakai di
Users (blokir, kredit, plan, reset password, paksa logout), Plans, Tasks (batalkan/ulangi),
Settings AI/Platform/YouTube Cookies, logout (header + dropdown), dan halaman login admin.

**Loading per rute**

- `admin/src/app/dashboard/loading.tsx` → skeleton + spinner orbit saat server component
  mengambil data (berlaku untuk semua sub-rute dashboard).
- `frontend/src/app/dashboard/loading.tsx` → kartu shimmer + spinner saat studio dimuat.
- Login/register/profile memakai spinner pada tombol simpan dan loader halaman.
- Dashboard publik menampilkan `ProcessingBar` (shimmer) selama ada task `queued`/
  `processing`, plus spinner kecil di badge status dan kartu task.

## Sesi & logout

- Login admin memakai endpoint user biasa (`POST /api/auth/login`) lalu aplikasi admin
  menyimpan **dua cookie httpOnly**: `clipzi_admin_token` (12 jam) dan
  `clipzi_admin_refresh` (30 hari).
- Access token backend hanya berlaku **60 menit** (`ACCESS_TOKEN_MINUTES`). Middleware
  admin (`admin/src/proxy.ts`) membaca `exp`; bila sisa < 2 menit ia memanggil
  `/api/auth/refresh` dan menulis cookie baru → sesi terasa "tidak pernah habis"
  selama admin aktif.
- **Logout** ada di tiga tempat: dropdown user (sidebar), ikon di header, dan command
  palette. Aksi ini memanggil `POST /api/admin/auth/logout` (audit), menghapus kedua
  cookie, lalu redirect ke login.
- **Logout semua perangkat** (`/api/admin/auth/logout-all`) mencabut semua token lewat
  tabel `auth_revocations` (kolom `revoked_before`): token dengan `iat` lebih lama
  ditolak sampai user login lagi. Tabel dibuat otomatis saat startup.
- Paksa logout user dari dashboard memakai mekanisme yang sama:
  `POST /api/admin/users/{id}/force-logout`.

## Branding (logo, favicon, nama)

Branding disimpan di `platform_settings` key `branding` dan **satu sumber** untuk
seluruh aplikasi:

- `frontend/src/components/BrandingProvider.tsx` — context + `<BrandLogo />`,
  `<BrandMark />`, `<BrandName />`. Dipakai di landing, login, register, dashboard,
  profile, footer, dan navbar (tidak ada lagi `▶ Clipzy AI` hardcode).
- `GET /api/branding` mengembalikan `version` (hash) + `Cache-Control: no-store`,
  sehingga logo/favicon baru langsung terpakai dan ikon tab tidak nyangkut cache.
- Accent color disuntik ke CSS variable `--ui-gold` (berubah tanpa reload).
- Upload di admin (`Settings › Branding`):
  - kartu **Logo / Favicon / OG** dengan pratinjau nyata (logo di atas latar gelap
    & terang, favicon di mockup tab browser, OG di kartu sosial),
  - info **dimensi & ukuran file**, drag & drop, preview instan sebelum upload selesai,
  - URL form langsung diperbarui setelah upload (tidak perlu reload),
  - file disimpan unik (`branding/<kind>/<uuid>.<ext>`) + `Cache-Control: immutable`.

## Monitoring VPS (realtime)

Tab **System** menampilkan kondisi VPS yang diperbarui tiap 3 detik.

```
host (systemd, loop 5 s)                        API (container)              admin (browser)
deploy/clipzi-host-metrics.py  --POST-->  /api/internal/host-metrics  -->  GET /api/admin/system/host
  /proc/stat, /proc/meminfo                 ring buffer 240 sampel         polling 3 s (route handler
  /proc/loadavg, statvfs /                  + rate jaringan                 /api/system/host)
  /proc/net/dev
  docker ps + docker stats
```

Kenapa agent: container API tidak punya akses ke CPU/RAM/disk host maupun docker
socket, jadi agent membaca host lalu mengirim JSON (hanya membaca, tanpa eskalasi izin).

Data yang ditampilkan: CPU % (+load 1/5/15), RAM & swap, disk `/`, rate jaringan
masuk/keluar, uptime, daftar container (state, CPU, RAM), antrean task
(`queued`/`processing`), dan jumlah worker Vast aktif. Badge **live/stale** menunjukkan
apakah agent masih mengirim data (>20 s tanpa data = stale).

Pasang di VPS (sekali):

```bash
install -m 755 deploy/clipzi-host-metrics.py /usr/local/sbin/clipzi-host-metrics.py
install -m 644 deploy/clipzi-host-metrics.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now clipzi-host-metrics
journalctl -u clipzi-host-metrics -n 20 --no-pager
```

Agent membaca `CLIPZI_WORKER_TOKEN` dari `backend/.env` dan mengirim ke
`http://127.0.0.1:8000` (port backend dipublish ke loopback di compose VPS).

## Proxy YouTube (filter aktif otomatis)

YouTube memblokir banyak IP datacenter (respons hanya storyboard / minta login).
Selain cookies dan PO token, sistem mendukung **pool proxy** dengan filter otomatis.

1. **Upload banyak file** `.txt/.csv` (drag & drop) atau paste teks di
   `Settings › YouTube Cookies › Proxy`.
2. Engine `app/services/proxy_parser.py` menormalkan semua format umum menjadi
   `scheme://[user:pass@]host:port`:

   ```
   host:port                 -> http://host:port
   host:port:user:pass       -> http://user:pass@host:port
   user:pass@host:port       -> http://user:pass@host:port
   socks5://host:port        -> socks5://host:port   (port 1080/1081/9050/9150 otomatis SOCKS)
   label|host:port           -> label disimpan
   # komentar, baris kosong, pemisah koma/; /tab diabaikan/diterima
   ```

3. Klik **START FILTER ACTIVE PROXY**: setiap proxy diuji paralel
   (`api.ipify.org` + opsional `youtube.com/generate_204`). Hanya yang aktif yang
   disimpan; yang mati dibuang; urut berdasarkan latency.
4. Hasilnya digenerate menjadi satu file **`active.txt`** (tombol Unduh) dan
   **otomatis dipakai** worker: `settings.YTDLP_PROXY` + env `YTDLP_PROXY_POOL`
   (rotasi maks 3 proxy per task). Endpoint fallback untuk worker:
   `GET /api/internal/proxies/active.txt`.

Urutan percobaan downloader: **cookies (L1) → tanpa cookies (L2) → proxy (L3/L4)**, dengan
player-client ladder (default → web → android/ios → tv_embedded).

## Storage multi-provider (Primary + Mirror)

Semua upload memakai satu pintu: `app/services/storage_registry.py` → `get_storage()`.

- Provider yang didukung (semua S3-compatible): **Cloudflare R2, Backblaze B2, AWS S3,
  Wasabi, DigitalOcean Spaces, Linode/Akamai, Scaleway, Hetzner, Supabase Storage,
  GCS (S3 interop), IDrive e2, Storj, Filebase, MinIO/custom**.
- Data di `platform_settings` key `storage`: `primary_id`, `mirror_ids`, `items[]`.
  Kredensial **AES-256-GCM**, UI hanya menampilkan mask (`AKI***PLE`).
- Migrasi aman: bila belum ada konfigurasi, otomatis diseed dari env `R2_*`
  (id `env-r2`) sehingga deployment lama tidak berubah.
- Upload ditulis ke **primary**, lalu **direplikasi background** ke mirror.
  Tombol **Sync mirror** menyalin objek yang belum ada (maks 200 per klik).
- Aksi di `Settings › Storage`: tambah/edit, **Uji** (put→head→delete), jadikan
  **primary**, toggle **mirror**, hapus, dan **Sync**.

## AI provider & daftar model

Semua provider memakai API chat-completions yang kompatibel OpenAI, jadi satu klien
menangani semuanya. Base URL bawaan otomatis dipakai bila kolom Base URL dikosongkan:

| Provider | Base URL bawaan | Model default |
|---|---|---|
| openai | `https://api.openai.com/v1` | `gpt-4o-mini` |
| openrouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` |
| groq | `https://api.groq.com/openai/v1` | `llama-3.1-8b-instant` |
| together | `https://api.together.xyz/v1` | `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` |
| deepseek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| mistral | `https://api.mistral.ai/v1` | `mistral-small-latest` |
| xai | `https://api.x.ai/v1` | `grok-2-latest` |
| fireworks | `https://api.fireworks.ai/inference/v1` | `llama-v3p1-8b-instruct` |
| cerebras | `https://api.cerebras.ai/v1` | `llama3.1-8b` |
| sambanova | `https://api.sambanova.ai/v1` | `Meta-Llama-3.1-8B-Instruct` |
| perplexity | `https://api.perplexity.ai` | `sonar` |
| gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-1.5-flash` |
| moonshot | `https://api.moonshot.ai/v1` | `moonshot-v1-8k` |
| zhipu | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| ollama | `http://localhost:11434/v1` | `llama3.1` |
| vllm | `http://localhost:8000/v1` | (isi manual) |
| azure | `https://<resource>.openai.azure.com/openai/v1/?api-version=...` | (nama deployment) |
| custom | (wajib diisi) | (isi manual) |

Cara pakai: Settings › AI → pilih provider → isi API key → **Simpan** → daftar model
otomatis dimuat → pilih model lewat dropdown (ada kolom pencarian). Tombol
**Muat daftar model** memanggil `GET {base_url}/models` di sisi server (timeout 20 s,
cache 5 menit) sehingga API key tidak pernah dikirim ke browser.

Bila provider tidak punya `/models`, nama model tetap bisa diketik manual. **Test
Connection** memanggil `chat/completions` mini dan menampilkan latensi, sample, serta
pesan error apa adanya (status + body) supaya mudah didiagnosis.

Perubahan provider tidak butuh rebuild: nilai disimpan di `platform_settings` key `ai`,
API key dienkripsi Fernet, lalu di-inject ke environment + `settings` yang hidup.
Worker memuatnya di awal setiap task (`load_and_apply_ai_config`).

## Cookies YouTube (base64 / Netscape)

yt-dlp butuh cookies untuk video yang meminta login/usia. Dua mode yang didukung:

1. **Rotasi DB (disarankan)** - cookies disimpan per baris di `ytdlp_cookies`
   (AES-256-GCM). `cookie_store.acquire()` memilih cookie aktif yang paling lama tidak
   dipakai, dan `sync_back()` menyimpan token hasil refresh yt-dlp kembali ke DB.
   Cooker yang gagal 3× otomatis ditandai `expired`.
2. **Base64 env** - base64 dari `cookies.txt`, disimpan terenkripsi di
   `platform_settings` key `youtube` dan di-inject ke `YTDLP_COOKIES_BASE64`
   (dipakai `downloader.py`). Cocok bila worker hanya membaca env.

Di dashboard: Settings › YouTube Cookies → tempel **base64** (boleh dengan prefix
`data:text/plain;base64,`) atau isi `cookies.txt`, isi label, pilih mode, lalu **Simpan
cookies**. Backend otomatis: decode → validasi format Netscape (harus ada domain
youtube.com) → simpan. Tabel menampilkan status, jumlah sukses/gagal, error terakhir,
tombol **Uji**, **Aktifkan/Nonaktifkan**, **Hapus**.

Membuat base64 dari file:

```bash
base64 -w0 cookies.txt > cookies.b64      # Linux
certutil -encode cookies.txt cookies.b64  # Windows (buang header/footer)
```

Ekspor base64 cookies yang sudah tersimpan (untuk ditempel ke env worker):

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  https://admin.<domain>/api/admin/ytdlp-cookies/<id>/base64 | jq -r .base64
```

## Setelan ekosistem & ganti domain (1 klik)

Semua nilai disimpan di `platform_settings` key `platform`:
`site_url`, `admin_url`, `support_email`, `timezone`, `maintenance_mode`,
`signup_enabled`, `google_client_id`, plus status domain
(`pending_domain`, `applied_domain`, `domain_status`).

Alur (opsi A - agent di host):

```
admin  -> POST /api/admin/settings/platform/apply-domain {domain, admin_domain}
       -> DB: domain_status = pending
agent  -> GET  /api/internal/domain-task          (header X-Clipzi-Token)
       -> backup .env -> set DOMAIN/ADMIN_DOMAIN
       -> docker compose up -d caddy
       -> opsional: Cloudflare DNS A record (proxied)
       -> POST /api/internal/domain-applied {ok, error}
       -> DB: domain_status = applied (atau failed + pesan error)
```

Pasang agent di VPS (sekali saja):

```bash
install -m 755 deploy/clipzi-domain-sync.sh /usr/local/sbin/clipzi-domain-sync.sh
install -m 644 deploy/clipzi-domain-sync.service /etc/systemd/system/
install -m 644 deploy/clipzi-domain-sync.timer   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now clipzi-domain-sync.timer
systemctl list-timers | grep clipzi-domain-sync
journalctl -u clipzi-domain-sync.service -n 30 --no-pager   # log penerapan
```

Variabel opsional di `.env` untuk update DNS otomatis:
`CLOUDFLARE_API_TOKEN` (izin Zone.DNS Edit) dan `CLOUDFLARE_ZONE_ID`.

Yang ikut berubah otomatis ketika `site_url` disimpan: `FRONTEND_URL` (link email &
redirect YouTube), origin CORS tambahan, dan `runtime-env` frontend. **Belum otomatis**
(kerjakan manual setelah tombol ditekan): redirect URI OAuth Google/YouTube di Google
Cloud Console, policy Cloudflare Access untuk subdomain admin, dan webhook Duitku.

Rollback cepat: Settings › Platform → isi domain lama → **Terapkan domain**, atau
kembalikan file backup `.env` di `/var/lib/clipzi-domain-sync/` lalu
`docker compose up -d caddy`.

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
| **Semua menu admin "Something went wrong"** | Access token 60 menit kedaluwarsa. Pastikan cookie `clipzi_admin_refresh` ada; cek `docker logs clipzi-admin \| grep 401`. Login sekali lagi setelah update. |
| **AI Test HTTP 000 / timeout, Vast hang, API startup 502** | Outbound HTTPS container diblokir firewall. Diagnosa: `curl -s -o /dev/null -w '%{http_code}' https://example.com` (dari host, harus 200) vs `docker exec clipzi-api curl ...` (harus 200). Perbaiki: `deploy/clipzi-cf-firewall.sh` lalu `/usr/local/sbin/clipzi-cf-firewall.sh --check`. |
| **`clipzi-web` unhealthy / home 502** | `API_INTERNAL_URL` kosong atau host salah. Compose frontend harus punya `API_INTERNAL_URL: http://backend:8000`. |
| `[ai_failed] AI belum aktif` | Isi provider + API key di Settings > AI, tekan Test Connection |
| `ai_failed: 401` | API key salah/kadaluarsa, atau base URL bukan endpoint OpenAI-compatible |
| `ai_failed: 404 model` | Nama model tidak ada di provider — klik **Muat daftar model** lalu pilih dari daftar |
| `POST /ai/models` gagal 400 | Provider butuh Base URL (mis. `custom`) atau API key belum disimpan |
| Tombol Ban / adjust kredit error 422 | Versi lama mengirim query param; sekarang body JSON. Update admin app (`docker compose pull admin`). |
| Task lambat tanpa alasan | Cek `log_tail`; bila rerank dilewati, provider timeout - naikkan `timeout_seconds` |
| Instance gagal boot | `registry-1.docker.io` timeout: naikkan `VAST_BOOT_TIMEOUT` (900+), ulangi task |
| `Sign in to confirm you're not a bot` | YouTube minta cookies: unggah di Settings > YouTube Cookies (base64 atau Netscape) |
| Cookies selalu `expired` | Ekspor ulang cookies dari browser (mode incognito, login YouTube), unggah lagi, lalu **Uji** |
| **`Requested format is not available`** | Selector lama `bestvideo+bestaudio/best` gagal saat YouTube hanya memberi video-only/combined tertentu. Sejak 13 Nov 2026 worker memakai ladder `bv*…/bv*+ba/b/b*` + beberapa player client + retry tanpa cookies, dan menulis daftar format ke `worker.log` bila gagal. Bila masih gagal: unggah cookies (Settings › YouTube Cookies), cek versi yt-dlp di log worker, lalu lihat `formats_tersedia` di pesan error task. |
| **`Sign in to confirm you're not a bot`** (dari VPS/Vast) | YouTube menolak IP datacenter. **Wajib cookies**: Settings › YouTube Cookies (base64 atau Netscape) lalu ulangi task. Worker kini menambahkan HINT ini otomatis di pesan error task. |
| Semua proxy mati setelah START FILTER | Normal di daftar gratis. Upload file baru / uji ulang; hanya proxy aktif dipakai sistem. |
| Upload klip gagal: `storage belum dikonfigurasi` | Isi minimal satu provider di Settings › Storage (bucket + endpoint + keys) lalu **Uji**. |
| Mirror tertinggal | Settings › Storage › **Sync mirror** (200 objek per klik). |
| Unduhan sukses tapi transkripsi kosong | Video terunduh tanpa stream audio (fallback `b*`). Worker otomatis mengulang dengan format audio wajib; kalau tetap gagal → pesan task menyarankan unggah cookies. |
| Domain baru belum aktif setelah "Terapkan domain" | Cek `systemctl status clipzi-domain-sync.timer`, `journalctl -u clipzi-domain-sync.service -n 50`, dan status di Settings › Platform (harus `applied`) |
| Admin tampak "tidak berubah" setelah deploy | Compose admin memakai tag **`:admin`**, bukan `:latest`. Jalankan `docker pull sujinwo555/clipzi-admin:admin` lalu `docker compose -f docker-compose.admin.yml up -d --force-recreate admin`. |
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

1. **Cloudflare Access (Zero Trust)** - aplikasi self-hosted untuk `admin.proxyai.live`
   dengan policy allow hanya email `sujinwo555@gmail.com` dan
   `admin@proxyai.live`, session 6 jam. Ini satu-satunya lapisan proteksi
   (basic_auth Caddy sudah dihapus).

Di domain publik, `/api/admin/*` dibalas **404** (bukan 401) supaya endpoint tidak
terkonfirmasi. Dokumentasi API juga dibalas 404.

## Pindah VPS / setup dari nol (runbook lengkap)

Semua yang WAJIB dikonfigurasi saat pindah server, berurutan. Ganti
`<IP-VPS>` dengan IP baru, dan `admin.proxyai.live` bila domain berubah.

### 1. DNS (Cloudflare)

| Record | Type | Value | Proxy |
|---|---|---|---|
| `proxyai.live` | A | `<IP-VPS>` | **Proxied (oranye)** |
| `www` | CNAME | `proxyai.live` | Proxied |
| `admin` | A | `<IP-VPS>` | **Proxied (oranye)** |

SSL/TLS mode: **Full (strict)** (Caddy memakai Let's Encrypt).

### 2. Cloudflare Access (admin)

Zero Trust -> Access -> Applications -> Add -> Self-hosted:
- Application: `ClipzyAI Admin`, domain `admin.proxyai.live`, session **6 hours**
- Policy `Admin Only`: action **Allow**, include **Emails**:
  `sujinwo555@gmail.com`, `admin@proxyai.live`

Bila record `admin` masih DNS-only, Access TIDAK berfungsi (request langsung ke origin).

### 3. Firewall: port 80/443 hanya dari Cloudflare

Caddy berjalan di container, jadi ufw pada INPUT tidak berpengaruh. Aturan dipasang di
chain `DOCKER-USER` (IPv4 + IPv6) oleh script yang disertakan repo:

```bash
scp deploy/clipzi-cf-firewall.sh root@<IP-VPS>:/usr/local/sbin/
scp deploy/clipzi-cf-firewall.service root@<IP-VPS>:/etc/systemd/system/
ssh root@<IP-VPS> 'chmod +x /usr/local/sbin/clipzi-cf-firewall.sh \
  && /usr/local/sbin/clipzi-cf-firewall.sh \
  && systemctl daemon-reload && systemctl enable --now clipzi-cf-firewall'
```

Script mengambil daftar IP Cloudflare terbaru dari cloudflare.com/ips-v4 + ips-v6,
mengizinkan port 80/443 hanya dari range itu, lalu DROP sisanya. **Port 22 (SSH) tidak
disentuh.** Bila pengambilan daftar gagal, script berhenti tanpa mengubah aturan
(mencegah lockout). Daftar IP Cloudflare berubah sesekali -> jalankan ulang script
(atau `systemctl restart clipzi-cf-firewall`) setiap beberapa bulan.

Verifikasi:
```bash
# harus TIMEOUT (origin tertutup)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 10 \
  --resolve admin.proxyai.live:443:<IP-VPS> https://admin.proxyai.live/auth/sign-in
# harus 302 ke cloudflareaccess.com (jalur resmi)
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://admin.proxyai.live/auth/sign-in
# harus 200
curl -s -o /dev/null -w '%{http_code}\n' https://proxyai.live/api/health
```

### 4. Repo & environment

```bash
mkdir -p /opt/clipzi && cd /opt/clipzi
git clone https://github.com/jayras150/ClipziAI.git app
ln -sfn /opt/clipzi/app /root/ClipziAI
cp app/backend/.env.example app/backend/.env   # lalu isi
```

Variabel **wajib** di `backend/.env` (tidak bisa diatur dari dashboard):
`SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
`R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `R2_PUBLIC_DOMAIN`, `YOUTUBE_CLIENT_ID`,
`YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REDIRECT_URI`, `YOUTUBE_API_KEY`, `VAST_API_KEY`,
`VAST_WORKER_IMAGE=sujinwo555/clipzi-backend:worker`, `VAST_GPU_FILTER`,
`VAST_BOOT_TIMEOUT=900`, `CLIPZI_WORKER_TOKEN`, `CLIPZI_CALLBACK_URL`,
`DUITKU_*` (payment), `SMTP_*` (email), `ADMIN_EMAILS`.

Nilai AI (provider, API key, model) **tidak** perlu di .env - diatur di dashboard admin.

### 5. Compose + Caddy

File yang dipakai di VPS:

| File | Isi |
|---|---|
| `docker-compose.vps.yml` | backend (api), frontend, caddy; env `DOMAIN`, `ADMIN_DOMAIN`, `ADMIN_BASIC_AUTH` (opsional) |
| `docker-compose.admin.yml` | service `admin` (image `sujinwo555/clipzi-admin:admin`, `CLIPZI_API_URL=http://backend:8000`) |
| `deploy/Caddyfile` | site publik + site admin + 404 `/api/admin/*` di domain publik |
| `deploy/clipzi-cf-firewall.sh` | firewall Cloudflare-only |

Env penting service `frontend` di compose: `NEXT_PUBLIC_API_URL` (untuk browser) dan
`API_INTERNAL_URL=http://backend:8000` (fetch server-side: judul/favicon dari branding).
Tanpa `API_INTERNAL_URL`, render server akan mencari host `backend` dan halaman bisa
menggantung bila API lambat.

Deploy pertama:
```bash
docker compose -f docker-compose.vps.yml -f docker-compose.admin.yml up -d --build
```

### 6. Database & seed

`init_db()` membuat tabel otomatis saat API start (`create_all`). Setelah container hidup:
```bash
docker exec clipzi-api python -m scripts.seed_pricing        # harga paket
# akun admin: daftar lewat aplikasi lalu pastikan email ada di ADMIN_EMAILS
docker exec clipzi-api python -c "import asyncio; from app.db.session import init_db; asyncio.run(init_db())"
```

### 7. Vast.ai

Worker menerima rahasia lewat env-var Vast (bukan argumen):
```bash
vastai create env-var DATABASE_URL "postgresql+asyncpg://..."
vastai create env-var R2_ACCESS_KEY_ID "..."
vastai create env-var R2_SECRET_ACCESS_KEY "..."
vastai create env-var R2_ENDPOINT_URL "..."
vastai create env-var R2_BUCKET_NAME "..."
vastai create env-var R2_PUBLIC_DOMAIN "..."
vastai create env-var CLIPZI_WORKER_TOKEN "..."
vastai create env-var SECRET_KEY "..."
```
Image worker = `sujinwo555/clipzi-backend:worker` (di-push oleh GitHub Actions).
Vast tidak punya webhook: supervisor memantau instance tiap 5 detik dan worker
mengirim callback HMAC ke `CLIPZI_CALLBACK_URL`.

### 8. Verifikasi setelah pindah

```bash
curl -s -o /dev/null -w 'health=%{http_code}\n' https://proxyai.live/api/health          # 200
curl -s -o /dev/null -w 'admin=%{http_code}\n'  https://admin.proxyai.live/auth/sign-in  # 302 (Access)
curl -s -o /dev/null -w 'adm_api=%{http_code}\n' https://proxyai.live/api/admin/system/stats # 404
docker ps --format '{{.Names}} {{.Status}}'                                                # api/web/caddy/admin healthy
docker exec clipzi-api env | grep -c VAST_API_KEY                                         # >= 1
```
Login admin (setelah lolos Cloudflare Access) -> Settings > AI -> **Test Connection** harus `ok`.

### 9. Backup & restore

```bash
bash scripts/backup-all.sh                 # satu arsip lengkap (db + repo + config)
bash scripts/restore-all.sh <arsip>        # restore ke VPS baru
```

### 10. Update rutin

```bash
git pull
docker compose -f docker-compose.vps.yml -f docker-compose.admin.yml pull backend
docker compose -f docker-compose.vps.yml -f docker-compose.admin.yml up -d
docker builder prune -af && docker image prune -af   # bila disk menipis
```

