# Clipzi AI

**Turn Long Videos → Viral Shorts in One Click**

[🇮🇩 Bahasa Indonesia](README.md) · 🇬🇧 **English**

Full-stack platform: FastAPI (backend) + Next.js 14 (frontend), with AI for
viral scoring, auto subtitles, 9:16 smart crop, and auto-upload to YouTube.

| Item | Value |
|------|-------|
| Version | 1.0.0 |
| Backend | Python 3.11/3.12 · FastAPI 0.115.6 · SQLAlchemy 2.0 (async) |
| Frontend | Next.js 14.2 · React 18 · TypeScript 5.9 · TailwindCSS |
| Database | PostgreSQL (Supabase) — 31 tables |
| Cache / Queue | Redis (Upstash) |
| Object Storage | Cloudflare R2 |
| API paths | 63 paths (see `GET /openapi.json`) |
| Containers | 2 separate images: `clipzi-backend`, `clipzi-frontend` |

---

## 📑 Table of Contents

1. [Architecture](#-architecture)
2. [Repository Structure](#-repository-structure)
3. [Features](#-features)
4. [Prerequisites](#-prerequisites)
5. [Quick Start (local)](#-quick-start-local)
6. [Environment Configuration](#-environment-configuration)
7. [🐳 Build & Upload to Docker Hub](#-build--upload-to-docker-hub) ← **full guide**
8. [Running Containers](#-running-containers)
9. [Hybrid Architecture: VPS + Serverless](#-hybrid-architecture-vps--vastai-serverless)
10. [AI & Transcription Providers](#-ai--transcription-providers)
11. [yt-dlp Cookies & Auto Rotation](#-yt-dlp-cookies--auto-rotation)
12. [Database & Migrations](#-database--migrations)
13. [Redis (Upstash)](#-redis-upstash)
14. [API Reference](#-api-reference)
15. [Pricing](#-pricing)
16. [Security](#-security)
17. [Android Integration](#-android-integration)
18. [Troubleshooting](#-troubleshooting)
19. [Contributing & License](#-contributing--license)

---

## 🏗 Architecture

```
┌──────────────────┐        HTTPS/JSON        ┌────────────────────┐
│  Frontend        │ ───────────────────────► │  Backend           │
│  Next.js :3000   │ ◄─────────────────────── │  FastAPI :8000     │
└────────┬─────────┘      (JWT Bearer)        └─────────┬──────────┘
         │                                              │
         │ public file URL                              ├──► PostgreSQL (Supabase)
         ▼                                              ├──► Redis (Upstash)
┌──────────────────┐                                    └──► Cloudflare R2
│  Cloudflare R2   │  ◄── rendered output upload
└──────────────────┘
```

The application is **stateless** — no state is kept on any server:

| Data | Stored in |
|------|-----------|
| Users, tasks, clips, credits, subscriptions | PostgreSQL (Supabase) |
| Cache, rate limit, progress | Redis (Upstash) |
| Videos & rendered files | Cloudflare R2 |
| Login session | JWT in browser `localStorage` |

As a result, frontend and backend **may run on different machines**, and
restarting the backend does not log users out.

---

## 📁 Repository Structure

```
ClipziAI/
├── backend/
│   ├── app/
│   │   ├── api/            # public + admin routers
│   │   ├── core/           # config, security (AES-GCM), redis
│   │   ├── db/             # async engine + init_db()
│   │   ├── models/         # 31 SQLAlchemy models
│   │   ├── schemas/        # Pydantic
│   │   └── services/       # AI, transcriber, downloader, cookie_store, storage, pipeline
│   ├── deployments/        # HTTP worker for Vast.ai (CLIPZI_ROLE=worker)
│   ├── alembic/            # (no migrations yet — see §Database)
│   ├── Dockerfile          # backend image (multi-stage)
│   ├── requirements.txt    # pinned versions (see note)
│   └── .env.example
├── frontend/
│   ├── src/app/            # App Router (page, login, register, dashboard)
│   ├── src/lib/            # api client, runtime env, i18n
│   ├── src/types/          # *.css / asset declarations
│   ├── public/             # runtime-env.js (created by container)
│   ├── Dockerfile          # frontend image (standalone)
│   └── docker-entrypoint.sh
├── scripts/
│   ├── build-and-push.ps1  # build & push (Windows)
│   ├── build-and-push.sh   # build & push (Linux/macOS/Vast.ai)
│   ├── encode_cookies.py   # cookies.txt -> base64
│   ├── check_ytdlp_cookies.py  # cookie health check (cron)
│   ├── seed_pricing.py
│   └── grant_signup_credits.py
├── deploy/                  # VPS: Caddyfile + compose + deploy & migration guide
├── docker-compose.yml       # dev: build from source (backend+db+frontend)
├── docker-compose.prod.yml  # prod: use images from Docker Hub
├── pyrightconfig.json       # Pylance: extraPaths + venv
└── .vscode/settings.json    # interpreter & TS SDK
```

---

## ✨ Features

### Video Editing (30+ features)
| Category | Features |
|----------|----------|
| **Framing** | 9:16 smart crop, blur background, contrast/brightness |
| **Zoom** | Auto zoom (face), auto zoom (audio), Ken Burns effect |
| **Tracking** | Object tracking |
| **Subtitle** | Auto subtitle (Whisper), karaoke, animated captions, 30+ languages, title card |
| **Audio** | Silence removal, background music, audio ducking, noise reduction, voice enhancement, sound effects |
| **Visual** | Color grading, video filters, speed ramp, transitions |
| **Branding** | Custom watermark, stickers/emoji, progress bar, intro/outro, end screen |
| **AI** | Viral scoring, AI titles & tags, AI thumbnail |

### Distribution
- YouTube upload (OAuth2, `access_type=offline` → refresh token stored encrypted)
- Scheduled publish (YouTube, TikTok, Instagram, Facebook)
- Multi-platform repurpose (one video → many platforms)
- Bulk processing (one long video → many clips)

### Account & Billing
- Email/password login (Argon2id) or social (Google, X/Twitter, Facebook)
- 2FA TOTP + backup codes
- Plans: Free, Standard, Pro, Team
- Credit system (5 free credits on signup)
- Duitku payment gateway + webhook callback
- Automatic invoices (PDF)

### Security & Admin
- Admin dashboard with RBAC (Super Admin, Admin, Moderator)
- Full audit trail
- AES-256-GCM field encryption (e.g. YouTube refresh tokens, yt-dlp cookies)
- Redis-based rate limiting (per IP & per API key)
- Content moderation & copyright checks
- GDPR/PDP compliance (data export/delete)

---

## ✅ Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11 / 3.12 | 3.11 is used in the Docker image |
| Node.js | 20 LTS | for the frontend |
| Docker Desktop | latest | **must be running** to build images |
| ffmpeg | optional | only when running the backend without Docker |
| Supabase / Upstash / Cloudflare R2 accounts | — | or local Postgres + Redis |

---

## 🚀 Quick Start (local)

### 1. Backend

```bash
cd backend

# 1. Create a virtualenv (once)
python -m venv .venv

# 2. Activate it
#    Windows PowerShell:
.venv\Scripts\Activate.ps1
#    Linux / macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
#   then fill in DATABASE_URL, REDIS_URL, R2_*, SECRET_KEY, ENCRYPTION_KEY
#   and at least one AI_API_KEY

# 5. Seed pricing plans (optional but recommended)
python ../scripts/seed_pricing.py

# 6. Run
uvicorn app.main:app --reload --port 8000
```

Verify:

```bash
curl http://localhost:8000/api/health      # {"status":"healthy","redis":"connected",...}
# Interactive docs: http://localhost:8000/docs
```

> ⚠️ **`requirements.txt` uses pinned versions** (`fastapi==0.115.6`,
> `starlette==0.41.3`, `sqlalchemy==2.0.36`, etc.). Do not bump majors without
> retesting — FastAPI 0.16x / Starlette 1.x changed the `app.routes` structure.
> `sqlalchemy[asyncio]` must keep the `[asyncio]` extra so `greenlet` is
> installed; without it the backend fails to start with `ImportError`.

### 2. Frontend

```bash
cd frontend
npm ci                 # use ci to respect package-lock.json
npm run dev            # http://localhost:3000
```

The frontend reads `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
For local development create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Quick smoke test

| Check | Command | Expected |
|-------|---------|----------|
| Backend alive | `curl localhost:8000/api/health` | `status: healthy` |
| Redis connected | response above | `redis: connected` |
| Frontend alive | open `localhost:3000` | landing page renders |
| Signup | open `/register` | new user receives 5 credits |

---

## ⚙️ Environment Configuration

All backend configuration lives in **one file**: `backend/.env`
(copy from `backend/.env.example`). That file is **never** committed and never
baked into the Docker image — values are injected at container runtime.

### Required variables (backend will not start without them)

| Variable | Example | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `fe3b37...` (64 hex) | JWT signing key. Generate: `python -c "import secrets;print(secrets.token_hex(32))"` |
| `ENCRYPTION_KEY` | `368984...` (64 hex) | AES-256-GCM key for sensitive fields |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/postgres` | **must** use the `postgresql+asyncpg://` prefix |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | project URL (not a key) |
| `SUPABASE_KEY` | `sb_secret_...` | server key, never expose to the frontend |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | — | Cloudflare R2 |
| `R2_ENDPOINT_URL` | `https://<account>.r2.cloudflarestorage.com` | |
| `R2_BUCKET_NAME` | `files` | |
| `R2_PUBLIC_DOMAIN` | `https://pub-xxxx.r2.dev` | public file domain |

### Other important variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `true` | **set `false` in production** — `DEBUG=true` makes SQLAlchemy log every query (slow + leaks data into logs) |
| `FRONTEND_URL` | `http://localhost:3000` | redirect target after YouTube OAuth |
| `CORS_ORIGINS` | `http://localhost:3000` | comma-separated frontend origins. Must match **exactly** (scheme+host+port) |
| `API_KEY_PREFIX` | `clipzy_` | prefix for user API keys. Put the prefix only, not the full example |
| `REDIS_URL` | `redis://localhost:6379/0` | Upstash: `rediss://default:<pass>@<db>.upstash.io:6379` |
| `AI_PROVIDER` | `openai` | `openai` / `groq` / `openrouter` / `together` / `deepseek` / `mistral` / `azure` / `ollama` / `custom` |
| `AI_API_KEY` | — | LLM provider key |
| `AI_BASE_URL` | — | optional; Ollama: `http://localhost:11434/v1` |
| `AI_MODEL` | — | model name on that provider |
| `TRANSCRIPTION_PROVIDER` | `local` | `local` (faster-whisper) or any OpenAI-compatible provider |
| `TRANSCRIPTION_BASE_URL` | — | **must be the `/v1` root**, not the full endpoint |
| `TRANSCRIPTION_MODEL` | — | e.g. `whisper-1`, `whisper-large-v3-turbo` |
| `WHISPER_MODEL` | `small` | `tiny`/`base`/`small`/`medium`/`large-v3` (`local` only) |
| `YOUTUBE_CLIENT_ID` / `_SECRET` | — | Google Cloud Console → OAuth 2.0 Client |
| `YOUTUBE_REDIRECT_URI` | `http://localhost:8000/api/youtube/callback` | must match the value registered in Google |
| `YOUTUBE_API_KEY` | — | for public data access |
| `DUITKU_MERCHANT_CODE` / `DUITKU_API_KEY` | — | payment gateway |
| `DUITKU_CALLBACK_URL` | `.../api/payment/callback` | **must be a public URL**, not localhost |
| `GOOGLE_/X_/FACEBOOK_CLIENT_ID` & `_SECRET` | — | social login |
| `MAX_VIDEO_DURATION_MINUTES` | `120` | input duration limit |
| `MAX_FILE_SIZE_MB` | `2000` | size limit |
| `OUTPUT_FPS` / `OUTPUT_RESOLUTION` | `30` / `1080x1920` | clip output |
| `YTDLP_COOKIES_BASE64` / `_FILE` | — | YouTube cookies (see §Cookies) |
| `YTDLP_COOKIE_MAX_FAILURES` | `3` | auto cookie rotation |
| `SMTP_*` | — | transactional email |

### ⚠️ 5 configuration traps

1. **`DATABASE_URL` with a sync driver** (`postgresql://`) → the async engine
   fails (`ModuleNotFoundError: psycopg2`). The code normalises it, but always
   write `postgresql+asyncpg://`.
2. **Supabase pooler port**: `5432` = session pooler (works with asyncpg),
   `6543` = transaction pooler (avoid for prepared statements).
3. **`TRANSCRIPTION_BASE_URL` set to the full endpoint**
   (`.../v1/audio/transcriptions`) → the SDK appends `/audio/transcriptions`
   again → **404**. Use the `/v1` root only.
4. **`CORS_ORIGINS` mismatch** with the frontend origin → the browser blocks the
   request with *blocked by CORS policy*.
5. **`DEBUG=true` in production** → logs full of queries and user data.

### Callback URLs for developer consoles

| Platform | Callback URL |
|----------|--------------|
| YouTube OAuth | `http://localhost:8000/api/youtube/callback` |
| Google Login | `http://localhost:8000/api/auth/google/callback` |
| X/Twitter Login | `http://localhost:8000/api/auth/x/callback` |
| Facebook Login | `http://localhost:8000/api/auth/facebook/callback` |
| Duitku | `https://<public-domain>/api/payment/callback` |

> Google **rejects** `http://` redirect URIs other than `localhost`. For
> production you need HTTPS + a domain (reverse proxy / Cloudflare Tunnel).

---

## 🐳 Build & Upload to Docker Hub

This guide goes from zero to an image that runs on another server.
Follow it **in order** — every step lists the command and the expected result.

> **Important:** building does **not** need `backend/.env`. All secrets are only
> required at `docker run` time (`--env-file`). The image is safe to share.

### 7-step overview

| # | Step | Core command |
|---|------|--------------|
| 0 | Make sure Docker is running | `docker version` |
| 1 | Choose the image name | `$DH_USER`, `$TAG` |
| 2 | Log in to Docker Hub | `docker login` |
| 3 | Build backend | `docker build ... backend` |
| 4 | Build frontend | `docker build ... frontend` |
| 5 | Test before pushing | `docker run ...` |
| 6 | Push both images | `docker push ...` |
| 7 | Pull on another server | `docker pull ...` |

---

### Step 0 — Make sure Docker is running

**Windows (PowerShell) / Linux / Vast.ai:**

```bash
docker version
```

You should see (at the bottom):

```
Server: Docker Desktop 4.x.x (engine 27.x)
 Engine:
  Version: 27.x
```

If you get `failed to connect to the docker API ... dockerDesktopLinuxEngine`:

1. Open **Docker Desktop** → wait for **Engine running** (the whale icon stops animating)
2. Run `docker version` again
3. Still failing? Restart Docker Desktop and retry

> On **Vast.ai** Docker is preinstalled — this step usually passes immediately.

---

### Step 1 — Choose the image name

Docker Hub requires the format `<username>/<repo>:<tag>`

| Rule | ✅ Correct | ❌ Wrong | Reason |
|------|-----------|---------|--------|
| Username is mandatory | `budi/clipzi-backend` | `clipzi-backend` | push is rejected |
| **All lowercase** | `budi/clipzi-backend` | `Budi/Clipzi-Backend` | `invalid reference format` |
| No spaces | `budi/clipzi-backend` | `budi/clipzi backend` | same |
| No `https://` | `budi/clipzi-backend` | `https://hub.docker.com/budi` | same |
| Tag is free-form | `:1.0.0`, `:latest` | `:` (empty) | defaults to `latest` |

**Windows (PowerShell):**

```powershell
$DH_USER = "your-dockerhub-username"   # CHANGE
$TAG     = "1.0.0"                     # CHANGE if needed
```

**Linux / macOS / Vast.ai (bash):**

```bash
DH_USER="your-dockerhub-username"      # CHANGE
TAG="1.0.0"
```

> You do **not** have to create the repository manually — it is created on the
> first push (as **public**). If you want it **private**, create it first at
> hub.docker.com → *Create repository*.

---

### Step 2 — Log in to Docker Hub (once per machine)

```bash
docker login -u "$DH_USER"
```

Enter your Docker Hub **password**. Expected output:

```
Login Succeeded
```

**With 2FA enabled** a plain password fails (`unauthorized`). Create a token:
Docker Hub → *Account Settings* → *Security* → *New Access Token* with
**Read & Write**, then use that token as the password.

**Windows — if `$DH_USER` is not set in a new terminal:**

```powershell
docker login -u your-dockerhub-username
```

---

### Step 3 — Build the backend image

**Run from the repo root** (the folder containing `backend/` and `frontend/`).

```powershell
docker build -t "$DH_USER/clipzi-backend:$TAG" -f backend/Dockerfile backend
```

```bash
docker build -t "$DH_USER/clipzi-backend:$TAG" -f backend/Dockerfile backend
```

The same command without variables (if you prefer):

```bash
docker build -t budi/clipzi-backend:1.0.0 -f backend/Dockerfile backend
```

What each part means:

| Part | Meaning |
|------|---------|
| `docker build` | build an image from a Dockerfile |
| `-t budi/clipzi-backend:1.0.0` | resulting image name + tag |
| `-f backend/Dockerfile` | Dockerfile to use |
| `backend` (last argument) | **build context** — this folder is sent to Docker; `.env` is excluded via `backend/.dockerignore` |

Expected last line:

```
 => => naming to docker.io/budi/clipzi-backend:1.0.0
```

Duration: **5–15 minutes** on the first build (downloads ffmpeg + Python wheels);
much faster afterwards thanks to the layer cache.

**If the target server uses a different architecture** (e.g. an x86_64 Vast.ai
instance while you build on Apple Silicon):

```bash
docker build --platform linux/amd64 \
  -t "$DH_USER/clipzi-backend:$TAG" -f backend/Dockerfile backend
```

---

### Step 4 — Build the frontend image

```bash
docker build -t "$DH_USER/clipzi-frontend:$TAG" -f frontend/Dockerfile frontend
```

Without variables:

```bash
docker build -t budi/clipzi-frontend:1.0.0 -f frontend/Dockerfile frontend
```

> **`NEXT_PUBLIC_API_URL` is not needed at build time.** It is injected at
> container start by `frontend/docker-entrypoint.sh` → `/app/public/runtime-env.js`,
> so a single image works on localhost, a VPS, and Vast.ai.

Expected last line:

```
 => => naming to docker.io/budi/clipzi-frontend:1.0.0
```

---

### Step 5 — Check the build result

```powershell
docker images --filter=reference="$DH_USER/*"
```

```bash
docker images | grep "$DH_USER/clipzi"
```

Expected: **2 rows**

```
REPOSITORY                TAG     IMAGE ID       CREATED         SIZE
budi/clipzi-backend       1.0.0   a1b2c3d4e5f6   2 minutes ago   1.52GB
budi/clipzi-frontend      1.0.0   f6e5d4c3b2a1   1 minute ago    183MB
```

±800 MB for the backend is **normal** (ffmpeg + OpenCV + yt-dlp). `faster-whisper` is not installed by default.
If only one row appears, one build failed — scroll up and read the error.

---

### Step 6 — Test before pushing (recommended)

**Backend** (needs `backend/.env` because it talks to the real database & Redis):

```bash
docker run -d --name test-api -p 8000:8000 \
  --env-file backend/.env \
  "$DH_USER/clipzi-backend:$TAG"
```

Wait ~10 seconds, then:

```bash
curl http://localhost:8000/api/health
docker logs test-api --tail 20
```

Expected response:

```json
{"status":"healthy","redis":"connected","database":"connected","version":"1.0.0"}
```

If the container exits immediately (`docker ps` is empty), read
`docker logs test-api` — usually a required variable is missing in `.env`
(`SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL`, `SUPABASE_*`, `R2_*`).

Clean up:

```bash
docker rm -f test-api
```

**Frontend** (verify runtime env injection):

```bash
docker run -d --name test-web -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://localhost:8000 \
  "$DH_USER/clipzi-frontend:$TAG"

sleep 5
curl http://localhost:3000/runtime-env.js
docker rm -f test-web
```

Expected:

```js
window.__ENV__ = { NEXT_PUBLIC_API_URL: "http://localhost:8000" };
```

If it matches, the frontend image is portable.

---

### Step 7 — Push to Docker Hub

**Push the backend:**

```bash
docker push "$DH_USER/clipzi-backend:$TAG"
```

**Push the frontend:**

```bash
docker push "$DH_USER/clipzi-frontend:$TAG"
```

What you will see (layer by layer, then a summary):

```
The push refers to repository [docker.io/budi/clipzi-backend]
5f70bf18a086: Pushed
...
1.0.0: digest: sha256:9c1f...abc size: 1157
```

If the last line contains `digest: sha256:... size: ...` → **success**.

**Also tag `latest`** (so consumers can omit the version):

```bash
docker tag "$DH_USER/clipzi-backend:$TAG"  "$DH_USER/clipzi-backend:latest"
docker tag "$DH_USER/clipzi-frontend:$TAG" "$DH_USER/clipzi-frontend:latest"
docker push "$DH_USER/clipzi-backend:latest"
docker push "$DH_USER/clipzi-frontend:latest"
```

---

### Step 8 — Verify on Docker Hub

Open in a browser (replace `budi`):

| Image | URL |
|-------|-----|
| Backend | `https://hub.docker.com/r/budi/clipzi-backend/tags` |
| Frontend | `https://hub.docker.com/r/budi/clipzi-frontend/tags` |

Or from the terminal:

```bash
docker manifest inspect "$DH_USER/clipzi-backend:$TAG" | head -20
```

If tag `1.0.0` shows up on the Tags page (around 800 MB), the image is uploaded.

---

### Step 9 — Use the image on another server (VPS / Vast.ai)

```bash
# (for a private repo) log in on the target server first
docker login -u "$DH_USER"

# pull the images
docker pull "$DH_USER/clipzi-backend:$TAG"
docker pull "$DH_USER/clipzi-frontend:$TAG"

# run the backend — secrets are provided here, not baked into the image
docker run -d --name clipzi-api -p 8000:8000 \
  --env-file backend/.env \
  -v clipzi-cache:/app/.cache \
  --restart unless-stopped \
  "$DH_USER/clipzi-backend:$TAG"

# run the frontend — point it at the backend server IP
docker run -d --name clipzi-web -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://SERVER_IP:8000 \
  --restart unless-stopped \
  "$DH_USER/clipzi-frontend:$TAG"
```

Check:

```bash
curl http://SERVER_IP:8000/api/health
curl http://SERVER_IP:3000/runtime-env.js
```

On **Vast.ai**: paste `username/clipzi-backend:1.0.0` in the *Image* field, then
expose ports `8000` and `3000` in the instance settings.

---

### Step 10 — Full one-shot flow (copy-paste)

**Windows PowerShell** — change the first 2 lines, then run the whole block:

```powershell
$DH_USER = "your-dockerhub-username"
$TAG     = "1.0.0"

docker version
docker login -u $DH_USER
docker build -t "$DH_USER/clipzi-backend:$TAG"  -f backend/Dockerfile backend
docker build -t "$DH_USER/clipzi-frontend:$TAG" -f frontend/Dockerfile frontend
docker images --filter=reference="$DH_USER/*"
docker push "$DH_USER/clipzi-backend:$TAG"
docker push "$DH_USER/clipzi-frontend:$TAG"
```

**Linux / macOS / Vast.ai:**

```bash
DH_USER="your-dockerhub-username"
TAG="1.0.0"

set -e
docker version
docker login -u "$DH_USER"
docker build -t "$DH_USER/clipzi-backend:$TAG"  -f backend/Dockerfile backend
docker build -t "$DH_USER/clipzi-frontend:$TAG" -f frontend/Dockerfile frontend
docker images | grep "$DH_USER/clipzi"
docker push "$DH_USER/clipzi-backend:$TAG"
docker push "$DH_USER/clipzi-frontend:$TAG"
echo "DONE: $DH_USER/clipzi-backend:$TAG"
```

**Or use the provided helper script** (builds and pushes both images):

```powershell
./scripts/build-and-push.ps1 -DockerHubUser your-dockerhub-username -Tag 1.0.0
```

```bash
./scripts/build-and-push.sh your-dockerhub-username 1.0.0
```

| PS1 parameter | Bash (env) | Default | Purpose |
|---------------|-----------|---------|---------|
| `-DockerHubUser` | 1st arg | required | Docker Hub username |
| `-Tag` | 2nd arg | `latest` | image tag |
| `-Platform` | `PLATFORM` | `linux/amd64` | target architecture |
| `-BackendOnly` | `TARGET=backend` | — | backend only |
| `-FrontendOnly` | `TARGET=frontend` | — | frontend only |
| `-SkipPush` | `BUILD_ONLY=1` | — | build without pushing |

---

### ❗ Build/push errors and fixes

| Error message | Cause | Fix |
|---------------|-------|-----|
| `failed to connect to the docker API ...` | Docker Desktop is not running | Start Docker Desktop, wait for "Engine running" |
| `"docker build" requires exactly 1 argument` | Build context missing | End the command with `backend` or `frontend` |
| `unable to prepare context: path "backend" not found` | Not in the repo root | `cd` to the folder containing `backend/` & `frontend/` |
| `invalid reference format` | Uppercase letters, spaces, or `https://` in the name | Use `<user>/<repo>:<tag>`, all lowercase |
| `denied: requested access to the resource is denied` | Not logged in, or the name prefix ≠ login account | `docker login -u <user>` and match the prefix |
| `unauthorized: incorrect username or password` | Wrong password / 2FA enabled | Use an **Access Token** (Read & Write) |
| `no space left on device` | Disk full | `docker system prune -a -f`, rebuild |
| `exec format error` when running | Wrong architecture | Build with `--platform linux/amd64` |
| `toomanyrequests: ... pull rate limit` | Docker Hub rate limit | Log in before pulling, or use a private repo |

### 📌 Important notes

1. **Secrets never enter the image.** Building needs no `.env`; never use
   `ARG`/`ENV` for `SECRET_KEY` or API keys — they would be stored permanently in
   the image layers (visible via `docker history`).
2. **Private repo**: create it on Docker Hub before the first push, and
   `docker login` on the target server too.
3. **Rebuild is required** after changing `requirements.txt`, `package.json`, or a
   Dockerfile — an existing image never updates itself.
4. **Image size**: ±800 MB for the backend and ±180 MB for the frontend is
   normal. To shrink it, remove unused entries from `requirements.txt`.
5. **Without Docker Hub** — you can also `docker save` → `scp` → `docker load`:

```bash
docker save "$DH_USER/clipzi-backend:$TAG" | gzip > clipzi-backend.tar.gz
scp clipzi-backend.tar.gz user@server:/tmp/
# on the target server:
docker load < /tmp/clipzi-backend.tar.gz
```





## ▶️ Running Containers

### A. Two standalone containers (most common)

```bash
# 1. Backend — all secrets come from the .env file, never baked into the image
docker run -d \
  --name clipzi-api \
  -p 8000:8000 \
  --env-file backend/.env \
  -v clipzi-cache:/app/.cache \
  --restart unless-stopped \
  <user>/clipzi-backend:1.0.0

# 2. Frontend — API URL can be changed at any time
docker run -d \
  --name clipzi-web \
  -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://PUBLIC_IP:8000 \
  --restart unless-stopped \
  <user>/clipzi-frontend:1.0.0
```

Notes:

| Item | Explanation |
|------|-------------|
| `--env-file backend/.env` | the file is read **at runtime**, not bundled |
| `-v clipzi-cache:/app/.cache` | persists the yt-dlp cookie cache so rotated tokens survive restarts |
| `--restart unless-stopped` | auto-restart on crash or reboot |
| `-e NEXT_PUBLIC_API_URL=...` | written to `/app/public/runtime-env.js` at startup |

Day-to-day commands:

```bash
docker logs -f clipzi-api          # follow logs
docker inspect --format '{{.State.Health.Status}}' clipzi-api
docker restart clipzi-api          # env changed -> restart, no rebuild needed
docker rm -f clipzi-api clipzi-web
```

### B. Docker Compose — from source (development)

```bash
cp backend/.env.example backend/.env     # then fill in credentials
docker compose up -d --build             # backend + db(postgres) + frontend
docker compose logs -f backend
docker compose down
```

`docker-compose.yml` runs a local Postgres and an optional local Redis:

```bash
docker compose --profile local-redis up -d
# then set REDIS_URL=redis://redis:6379/0
```

### C. Docker Compose — from pushed images (production)

```bash
export DOCKERHUB_USER=<dockerhub-username>
export TAG=1.0.0
export NEXT_PUBLIC_API_URL=http://PUBLIC_IP:8000
docker compose -f docker-compose.prod.yml up -d
```

`docker-compose.prod.yml` contents:

| Service | Image | Port | Env |
|---------|-------|------|-----|
| `backend` | `${DOCKERHUB_USER}/clipzi-backend:${TAG}` | 8000 | `env_file: ./backend/.env` |
| `frontend` | `${DOCKERHUB_USER}/clipzi-frontend:${TAG}` | 3000 | `NEXT_PUBLIC_API_URL` |

### D. Capacity notes

- The **backend runs fine without a GPU**: transcription uses an API provider,
  and video rendering happens on the Vast.ai GPU worker.
- For higher throughput, move transcription to a cloud provider
  (`TRANSCRIPTION_PROVIDER=groq|openai`) to keep the instance CPU free.

---

## 🔀 Hybrid Architecture: VPS + Vast.ai Serverless

The API and frontend run on a **single always-on cheap VPS**, while the heavy
video processing runs on a **Vast.ai serverless GPU** that bills per second and
automatically scales to zero when idle.

```
        Browser
           │ HTTPS (single domain)
           ▼
┌──────────────────────── VPS (Docker) ────────────────────────┐
│  Caddy :80/:443  ──/api/*──►  backend FastAPI :8000          │
│                  ──/*─────►  frontend Next.js :3000          │
└───────────────────────────┬──────────────────────────────────┘
                            │
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
  Supabase            Upstash Redis        Cloudflare R2
  (PostgreSQL)        (cache/queue)        (video & files)
        ▲
        │ task status updates
┌───────┴──────────────────────────────────────────────────────┐
│ Vast.ai Serverless Endpoint (GPU, scale-to-zero)             │
│ Worker: deployments/worker_api.py → pipeline → upload to R2   │
└──────────────────────────────────────────────────────────────┘
```

### Why hybrid (instead of putting the whole API on serverless)?

| Reason | Explanation |
|--------|-------------|
| **Cold start** | An idle serverless endpoint must provision + boot first. If the whole API lived there, the user's first request (login, dashboard) would wait for it |
| **Cost** | GPUs are expensive; the API only needs CPU. Keeping the API always-on on a 1–2 GB VPS is far cheaper |
| **Webhooks** | Duitku callbacks and OAuth need an endpoint that is always ready |
| **Scaling** | GPU workers can scale 0→N without affecting the API |

### Components

| Component | Role | Managed by |
|-----------|------|------------|
| VPS + Caddy | Hosts the API & frontend, automatic HTTPS, single origin (no CORS) | `deploy/` |
| Vast **endpoint** | Router + autoscaling policy (`max_workers`, `inactivity_timeout`, …) | `scripts/vastai-setup.py create` |
| Vast **workergroup** | GPU worker pool: image, GPU filter, disk | same |
| Vast **worker** | Runs `deployments/worker_api.py` (`CLIPZI_ROLE=worker`) | automatically by Vast |
| Supabase / Upstash / R2 | Durable state (nothing on the VPS) | external services |

### One job's flow

1. User submits a task → API validates credits → stores the task (`status=queued`)
2. API dispatches the job to the Vast endpoint (`VAST_ENDPOINT_URL` or SDK)
3. Worker runs `run_video_pipeline(task_id)`: download → transcribe → cut → burn subtitles → upload to R2
4. Worker updates `task.status`/`progress`/`clips` in PostgreSQL
5. Frontend polls `GET /api/tasks/{id}`


### Deployment guide

The step-by-step guide (DNS, Docker, swap, verification, operations) lives in
**[`deploy/README.md`](deploy/README.md)**. Summary:

```bash
# --- on the VPS ---
git clone <REPO_URL> clipzi-ai && cd clipzi-ai
cp backend/.env.example backend/.env && nano backend/.env            # all secrets
cp deploy/.env.vps.example deploy/.env.vps && nano deploy/.env.vps   # DOMAIN, DOCKERHUB_USER, TAG

docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml pull
docker compose --env-file deploy/.env.vps -f deploy/docker-compose.vps.yml up -d

curl https://<DOMAIN>/api/health            # {"status":"healthy",...}
curl https://<DOMAIN>/runtime-env.js        # window.__ENV__ = {...}
```

```bash
# --- locally: prepare the GPU worker ---
pip install vastai
vastai set api-key <VAST_API_KEY>
python scripts/vastai-setup.py create       # endpoint + workergroup
python scripts/vastai-setup.py status       # read endpoint URL -> set VAST_ENDPOINT_URL
```

### Vast.ai CLI cheatsheet

| Command | Purpose |
|---------|---------|
| `python scripts/vastai-setup.py create` | create endpoint + workergroup (check `status` first to avoid duplicates) |
| `... update` | re-apply `VAST_MAX_WORKERS`, `VAST_TARGET_UTIL`, `VAST_INACTIVITY_TIMEOUT` |
| `... status` | show endpoint, URL, workergroup, worker count |
| `... logs --tail 200` | last 200 endpoint log lines (`vastai get endpt-logs`) |
| `... benchmark --gpus RTX_4090,RTX_3090` | find the best perf/$ GPU (`vastai run benchmarks`) |
| `... teardown` | delete workergroup + endpoint (worker billing stops) |
| `python scripts/vastai-setup.py --dry-run create` | print the `vastai` commands without running them |

Autoscaling parameters (from `backend/.env`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `VAST_MIN_WORKERS` | `0` | 0 = scale to zero when idle |
| `VAST_MAX_WORKERS` | `4` | parallel worker ceiling |
| `VAST_TARGET_UTIL` | `0.9` | target utilization |
| `VAST_INACTIVITY_TIMEOUT` | `300` | idle seconds before workers stop |
| `VAST_GPU_FILTER` | `gpu_ram>=16 disk_space>=40 inet_down>200` | marketplace filter |

> 💰 **Billing model**: `Ready`/`Loading` workers bill GPU per second; `Inactive`
> (cold) workers bill only storage + bandwidth; a `Destroyed` endpoint bills
> nothing. Hence `VAST_MIN_WORKERS=0` + `inactivity_timeout` is the cheapest setup.

### One image, two roles

The same backend image serves as API and worker; the role comes from an env var:

| `CLIPZI_ROLE` | Process | Used on |
|---------------|---------|---------|
| `api` (default) | `uvicorn app.main:app` (63 REST paths) | VPS |
| `worker` | `uvicorn deployments.worker_api:app` (`/health`, `/ready`, `/process`) | Vast worker |

### VPS migration / upgrade

Nothing durable lives on the VPS — only 3 config files need moving
(`backend/.env`, `deploy/.env.vps`, `deploy/Caddyfile`). Downtime: 1–3 minutes.

**Full walkthrough** (steps A–E, rollback, checklist):
**[`deploy/README.md` → 🚚 Migrasi / Upgrade VPS](deploy/README.md#-migrasi--upgrade-vps)**.

### Fallback: dedicated GPU instance

If you prefer not to use serverless, run API + worker as regular containers on a
dedicated GPU instance:

```bash
docker compose -f docker-compose.prod.yml up -d
```

You pay for the GPU 24/7 even without jobs — only sensible at sustained load.



## 🤖 AI & Transcription Providers

### LLM provider (viral scoring, titles, descriptions, tags)

One configuration for every AI feature — switch providers without touching code.

```env
# Provider: openai | groq | openrouter | together | deepseek | mistral | azure | ollama | custom
AI_PROVIDER=groq
AI_API_KEY=gsk_your-key
AI_MODEL=llama-3.1-8b-instant
# AI_BASE_URL may stay empty for built-in providers.
AI_BASE_URL=
```

Local **Ollama** (no API key):

```env
AI_PROVIDER=ollama
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3.1
AI_API_KEY=
```

For your own endpoint: `AI_PROVIDER=custom` + `AI_BASE_URL` (`/v1` root).
`OPENAI_API_KEY` is only a compatibility fallback when `AI_API_KEY` is empty.

### Transcription provider

```env
# Local (faster-whisper, CPU int8)
TRANSCRIPTION_PROVIDER=local
WHISPER_MODEL=small
```

```env
# Cloud (must be OpenAI /audio/transcriptions compatible), e.g. Groq
TRANSCRIPTION_PROVIDER=groq
TRANSCRIPTION_API_KEY=gsk_your-key
TRANSCRIPTION_BASE_URL=https://api.groq.com/openai/v1   # /v1 root, NOT the full endpoint
TRANSCRIPTION_MODEL=whisper-large-v3-turbo
```

API key fallback order: `TRANSCRIPTION_API_KEY` → `AI_API_KEY` → `OPENAI_API_KEY`.

| Local model | RAM ± | Accuracy | Speed |
|-------------|-------|----------|-------|
| `tiny` / `base` | ~1 GB | low–medium | fast |
| `small` | ~2 GB | good | balanced |
| `medium` | ~5 GB | better | slower |
| `large-v3` | ~10 GB | best | slow |

---

## 🍪 yt-dlp Cookies & Auto Rotation

yt-dlp does **not** use cookies automatically. Without cookies, downloads still
work for **public videos from residential IPs**, but fail on datacenter IPs
(Vast.ai / VPS / cloud) with:

```
Sign in to confirm you're not a bot
```

Add cookies **only if** you hit that error, or need age-restricted / private /
members-only videos.

### Option 1 — base64 (most practical for Docker)

```bash
# 1. Log in to YouTube in your browser, install the "Get cookies.txt LOCALLY" extension
# 2. Export -> cookies.txt
# 3. Encode it
python scripts/encode_cookies.py cookies.txt
```

Paste the result into `backend/.env`:

```env
YTDLP_COOKIES_BASE64=H4sIAAAA...     # one long line
```

The backend decodes it to `.cache/ytdlp_cookies.txt` on first use
(never baked into the image).

### Option 2 — file (mount)

```env
YTDLP_COOKIES_FILE=/app/cookies.txt
```

```bash
docker run -d -v "$PWD/cookies.txt:/app/cookies.txt:ro" ... <image>
```

### Option 3 — database cookie pool with auto rotation ⭐ (recommended for production)

Cookies live in the `ytdlp_cookies` table (AES-256-GCM encrypted), support
multiple accounts, and rotate automatically without redeploying:

```bash
# upload cookies (unique label per account)
curl -X POST http://localhost:8000/api/admin/ytdlp-cookies \
  -H "Content-Type: application/json" \
  -d '{"label":"account-1","cookies":"<cookies.txt content>"}'

# probe every cookie now
curl -X POST http://localhost:8000/api/admin/ytdlp-cookies/probe-all

# inspect the pool
curl http://localhost:8000/api/admin/ytdlp-cookies
```

| Mechanism | Automatic? | Description |
|-----------|-----------|-------------|
| Short-lived token refresh | ✅ | yt-dlp writes the cookie jar back to `cookiefile` (`YoutubeDL.save_cookies()`), then `sync_back()` re-encrypts it into the DB |
| Multi-account rotation | ✅ | `acquire()` picks the active cookie used least recently (round-robin) |
| Expiry detection | ✅ | `Sign in to confirm`, `cookies are no longer valid`, `HTTP 403`, or `fail_count >= YTDLP_COOKIE_MAX_FAILURES` → status `expired` |
| Failover | ✅ | `expired` cookies are skipped, downloads use the next account |
| Google re-login | ❌ | if the session is truly revoked, cookies must be exported manually |

Schedule a periodic check (every 6 hours):

```cron
0 */6 * * * cd /app/backend && python ../scripts/check_ytdlp_cookies.py >> /var/log/clipzi-cookies.log 2>&1
```

The script exits with code `1` when any cookie became `expired` — handy for alerting.

Cookie admin endpoints:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/admin/ytdlp-cookies` | list cookies (no content) |
| POST | `/api/admin/ytdlp-cookies` | upload/overwrite cookies |
| POST | `/api/admin/ytdlp-cookies/probe-all` | probe all + auto-expire |
| POST | `/api/admin/ytdlp-cookies/{id}/probe` | probe one |
| POST | `/api/admin/ytdlp-cookies/{id}/reactivate` | re-enable |
| POST | `/api/admin/ytdlp-cookies/{id}/disable` | disable |
| GET | `/api/admin/ytdlp-cookies/{id}/content` | view plaintext (debug) |
| DELETE | `/api/admin/ytdlp-cookies/{id}` | delete |

Extra options:

| Variable | Purpose |
|----------|---------|
| `YTDLP_PROXY` | residential proxy, e.g. `http://user:pass@ip:port` |
| `YTDLP_EXTRACTOR_ARGS` | e.g. `youtube:player_client=web_safari,android` |

> 🔐 **Cookies are login credentials.** Use a dedicated account (never your main
> one), never commit `cookies.txt`, and log out/rotate if the file leaks.
> `cookies.txt`, `.cache/`, and `downloads/` are already in `.gitignore` and
> `.dockerignore`.

---

## 🗄 Database & Migrations

| Item | Value |
|------|-------|
| Engine | PostgreSQL 15 (Supabase) |
| Driver | `asyncpg` via SQLAlchemy 2.0 async |
| Table count | **31** |
| Schema creation | automatic at startup (`Base.metadata.create_all`) |

```python
# app/db/session.py
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, pool_pre_ping=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### Important notes

1. **`create_all` never alters existing tables.** New tables → created
   automatically. Column changes/removals → **not** applied. Enable Alembic for
   schema changes (`alembic/versions` is still empty):

   ```bash
   cd backend
   alembic revision --autogenerate -m "change column x"
   alembic upgrade head
   ```

2. **`DEBUG=false` in production.** `DEBUG=true` sets `echo=True` → every SQL
   statement (including parameters) is logged.

3. **Supabase pooler limits.** The engine uses the default pool
   (`pool_size=5`, `max_overflow=10`). If you run more than one process
   (API + cron + worker), reduce it to avoid `too many connections`:

   ```python
   create_async_engine(url, pool_size=3, max_overflow=2, pool_pre_ping=True)
   ```

4. **Session vs transaction pooler**: use port `5432` (session) with asyncpg.

### Seeding initial data

```bash
cd backend
python ../scripts/seed_pricing.py          # Free/Standard/Pro/Team plans
python ../scripts/grant_signup_credits.py  # signup credits (optional)
```

---

## ⚡ Redis (Upstash)

Redis powers the ARQ job queue, rate limiting, caching, and task progress.
Durable data stays in PostgreSQL; video files in Cloudflare R2.

1. Open [console.upstash.com](https://console.upstash.com) → **Create Database**.
2. Go to the **Connect** tab → choose the **redis-cli / TCP** section (not REST API).
3. Copy the **password** from `redis-cli ... -a <PASSWORD>`.
4. Set it in `backend/.env`:

```env
REDIS_URL=rediss://default:<UPSTASH_PASSWORD>@<db-name>.upstash.io:6379
```

| Note | Detail |
|------|--------|
| `rediss://` is required | two `s` = TLS. **Not** the REST URL (`https://...`) |
| REST token ≠ password | REST tokens are for JS/Node only and are not used by this Python backend |
| Connection check | `GET /api/health` → `redis: connected` |
| Free tier | daily command quota applies; the ARQ worker polls |
| Local Redis | `docker compose --profile local-redis up -d` → `REDIS_URL=redis://redis:6379/0` |

---

## 📡 API Reference

Interactive docs: **`http://localhost:8000/docs`** · OpenAPI: `/openapi.json` (63 paths).

### Public

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Server health + Redis status |
| GET | `/api/formats` | Supported formats & resolutions |
| POST | `/api/auth/register` | Create account (+5 credits) |
| POST | `/api/auth/login` | Login → access + refresh token |
| POST | `/api/auth/refresh` | Refresh access token |
| POST | `/api/auth/2fa/setup` \| `/verify` | Enable TOTP 2FA |
| GET/PUT | `/api/users/me` | User profile |
| POST | `/api/tasks` | Create a video processing task |
| GET | `/api/tasks` \| `/api/tasks/{id}` | List / detail tasks |
| DELETE | `/api/tasks/{id}` | Delete a task |
| GET | `/api/editing/options` | Available editing features |
| POST | `/api/editing/validate` | Validate editing options |
| GET | `/api/pricing` | Pricing plans |
| POST | `/api/payment/create` | Create Duitku payment |
| POST | `/api/payment/callback` | Duitku webhook (public, must be reachable) |
| GET | `/api/credits/history` \| `/balance` | Credits |
| GET | `/api/analytics/*` | Clip performance stats |
| CRUD | `/api/api-keys` | API keys for integrations |
| CRUD | `/api/webhooks` | Webhook subscriptions |
| GET | `/api/youtube/auth-url` \| `/status` | YouTube OAuth |
| GET | `/api/youtube/callback` | OAuth callback (redirects to frontend) |
| CRUD | `/api/templates` | Clip templates |
| POST | `/api/bulk` | Bulk jobs |
| CRUD | `/api/scheduled-publish` | Scheduled publishing |
| CRUD | `/api/multi-platform` | Multi-platform repurpose |
| GET | `/api/compliance/*` | GDPR/PDP (export/delete data) |

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/auth/login` | Admin login |
| GET | `/api/admin/users` | List users |
| POST | `/api/admin/users/{id}/ban` | Ban a user |
| POST | `/api/admin/users/{id}/credits/adjust` | Adjust credits |
| CRUD | `/api/admin/plans` | Manage plans |
| GET | `/api/admin/tasks` · `POST /{id}/cancel` | Monitor & cancel tasks |
| GET | `/api/admin/transactions` | Transactions |
| GET | `/api/admin/audit` · `/audit/user/{id}/timeline` | Audit trail |
| GET | `/api/admin/security` | Security events |
| GET | `/api/admin/system/health` · `/stats` | Health & stats |
| * | `/api/admin/ytdlp-cookies` | yt-dlp cookie pool (see §Cookies) |

> ⚠️ **Security**: some `/api/admin/*` routes in this codebase do not yet use an
> auth guard (matching the project's initial pattern). Before production, add an
> admin verification dependency to every admin router — especially
> `/api/admin/ytdlp-cookies/{id}/content`, which returns plaintext cookies.

---

## 💰 Pricing

| Plan | Price/month | Credits | Max duration | Concurrent | Editing features | YouTube upload |
|------|-------------|---------|--------------|------------|------------------|----------------|
| Free | Free | 5 (one-time) | 5 minutes | 1 | Limited | ❌ |
| Standard | Rp 99,000 | 30 | 30 minutes | 2 | Partial | ✅ |
| Pro | Rp 249,000 | 100 | 60 minutes | 5 | All | ✅ |
| Team | Rp 499,000 | 300 | 120 minutes | 10 | All | ✅ |

Seed into the database: `python scripts/seed_pricing.py`

---

## 🔐 Security

| Aspect | Implementation |
|--------|----------------|
| Passwords | Argon2id (GPU-cracking resistant) |
| Tokens | JWT HS256 — access 15 minutes, refresh 7 days |
| Sensitive data | AES-256-GCM field-level encryption (`ENCRYPTION_KEY`) |
| yt-dlp cookies | stored encrypted in the `ytdlp_cookies` table |
| 2FA | TOTP (Google Authenticator compatible) + backup codes |
| Transport | TLS 1.3 required in production |
| Rate limiting | Redis, per IP and per API key |
| Audit | every admin & user action recorded |
| Secrets | `.env` is never committed or baked into images (`.gitignore` + `.dockerignore`) |

Pre-production checklist:

- [ ] `DEBUG=false`
- [ ] `SECRET_KEY` & `ENCRYPTION_KEY` rotated (do not ship the example values)
- [ ] `CORS_ORIGINS` limited to your real domains
- [ ] `/api/admin/*` routes protected by an admin auth guard
- [ ] `DUITKU_CALLBACK_URL` uses public HTTPS
- [ ] Database backups + Alembic enabled for schema changes

---

## 📱 Android Integration

Example API calls from an Android app (Kotlin + Retrofit):
```kotlin
// Create a task
val response = apiService.createTask(
    CreateTaskRequest(
        sourceUrl = "https://youtube.com/watch?v=xxx",
        editingOptions = mapOf("auto_zoom_face" to true),
        autoUploadYoutube = true
    )
)

// Poll status
val task = apiService.getTask(response.taskId)
```

Authentication uses `Authorization: Bearer <access_token>` or
`X-API-Key: clipzy_<key>` (created from the dashboard).

---

## 🧰 Troubleshooting

### Build & Docker

| Symptom | Fix |
|---------|-----|
| `failed to connect to the docker API` | Docker Desktop is not running |
| Backend container exits at startup | `docker logs <container>`; usually a missing required env var or missing `greenlet` (ensure `sqlalchemy[asyncio]`) |
| `exec format error` | rebuild with `--platform linux/amd64` |
| `ModuleNotFoundError: app` | build context must be the `backend` folder |

### Application

| Symptom | Cause |
|---------|-------|
| `ModuleNotFoundError: psycopg2` | `DATABASE_URL` is not `postgresql+asyncpg://` |
| `ImportError ... greenlet` | `sqlalchemy` installed without the `[asyncio]` extra |
| Transcription 404 | `TRANSCRIPTION_BASE_URL` contains the full endpoint; use the `/v1` root |
| Browser: *blocked by CORS* | `CORS_ORIGINS` does not match the frontend origin |
| Frontend calls `localhost:8000` | `NEXT_PUBLIC_API_URL` was not set when the container started |
| YouTube: *Sign in to confirm you're not a bot* | yt-dlp cookies required (§Cookies) |
| OAuth Google: *redirect_uri_mismatch* | `YOUTUBE_REDIRECT_URI` differs from Google's config, or uses `http://IP` (needs HTTPS/domain) |
| `?` on the dashboard | check `NEXT_PUBLIC_API_URL`, then open `/runtime-env.js` |

### Editor (VS Code)

| Symptom | Fix |
|---------|-----|
| Pylance: *Import "fastapi" could not be resolved* | select the `backend\.venv` interpreter (**Python: Select Interpreter**) — not `frontend\.venv` |
| TS: *Expression expected* in `layout.tsx` while `tsc` is clean | stale TS server → **TypeScript: Restart TS Server**, or **File: Revert File** if the buffer is dirty |
| `*.css` not recognised | the declarations live in `frontend/src/types/assets.d.ts` (must be script-mode, no `export`) |
| Odd diagnostics after creating a large venv | `files.watcherExclude` for `.venv` / `node_modules` (already configured) |

Quick verification from the terminal (source of truth, not the Problems panel):

```bash
cd frontend && npx tsc --noEmit          # must exit 0
cd backend  && .venv\Scripts\python.exe -c "from app.main import app; print(len(app.openapi()['paths']))"
```

---

## 🤝 Contributing & License

1. Fork → create a feature branch → commit → open a pull request.
2. Follow the existing code style; run `npx tsc --noEmit` (frontend) and
   `python -m compileall app` (backend) before pushing.
3. Never commit `.env`, `cookies.txt`, or any file containing credentials.

**License:** MIT








