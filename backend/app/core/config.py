from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Clipzi AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str
    API_KEY_PREFIX: str = "clipzy_"
    FRONTEND_URL: str = "http://localhost:3000"

    # Database (Supabase PostgreSQL)
    SUPABASE_URL: str
    SUPABASE_KEY: str
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Cloudflare R2
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_ENDPOINT_URL: str
    R2_BUCKET_NAME: str
    R2_PUBLIC_DOMAIN: str

    # YouTube Data API v3
    YOUTUBE_CLIENT_ID: Optional[str] = None
    YOUTUBE_CLIENT_SECRET: Optional[str] = None
    YOUTUBE_REDIRECT_URI: Optional[str] = None
    YOUTUBE_API_KEY: Optional[str] = None

    # Legacy OpenAI key (fallback for AI_API_KEY and TRANSCRIPTION_API_KEY)
    OPENAI_API_KEY: Optional[str] = None
    # Local faster-whisper fallback model (legacy-compatible)
    WHISPER_MODEL: str = "small"
    # Masa berlaku token. Access token pendek (default 1 jam) + refresh panjang
    # supaya sesi tidak memaksa login ulang, tapi token bocor tetap cepat mati.
    ACCESS_TOKEN_MINUTES: int = 60
    REFRESH_TOKEN_DAYS: int = 30
    # Folder cache model Whisper lokal. Kosong = default HuggingFace
    # (~/.cache/huggingface). Di container API diisi /app/.cache/huggingface
    # supaya model tidak diunduh ulang setiap container dibuat.
    WHISPER_CACHE_DIR: Optional[str] = None

    # AI Provider (any OpenAI-compatible LLM provider)
    # Provider: openai | groq | openrouter | together | deepseek | mistral | azure | ollama | custom
    AI_PROVIDER: str = "openai"
    AI_API_KEY: Optional[str] = None          # if AI_API_KEY is empty, falls back to OPENAI_API_KEY
    AI_BASE_URL: Optional[str] = None         # optional; provider default used when omitted
    AI_MODEL: Optional[str] = None            # optional; provider default model used when omitted
    AI_TEMPERATURE: float = 0.7
    AI_MAX_TOKENS: int = 2048

    # Audio transcription provider
    # Provider: local | gpu | openai | groq | together | custom
    # Non-local providers must expose the OpenAI-compatible /audio/transcriptions API.
    TRANSCRIPTION_PROVIDER: str = "local"
    TRANSCRIPTION_API_KEY: Optional[str] = None
    TRANSCRIPTION_BASE_URL: Optional[str] = None
    TRANSCRIPTION_MODEL: Optional[str] = None

    # Transkripsi Whisper di GPU worker (CTranslate2/faster-whisper, tanpa torch).
    # Nama model HuggingFace juga diterima: openai/whisper-large-v3 -> large-v3,
    # openai/whisper-large-v3-turbo -> turbo (lebih cepat, akurasi hampir sama).
    GPU_WHISPER_MODEL: str = "large-v3"

    # Izinkan fallback transkripsi ke provider API (OpenRouter dsb).
    # Produksi WAJIB False: transkripsi hanya Whisper lokal/GPU di instance.
    TRANSCRIPTION_ALLOW_REMOTE: bool = False

    # ---------- LLM lokal (llama.cpp server) di worker GPU Vast.ai ----------
    # Dipakai untuk rerank momen viral + metadata judul/deskripsi/tag, supaya
    # analisis AI tidak keluar dari instance (tanpa biaya API).
    LOCAL_LLM_ENABLED: bool = True
    LOCAL_LLM_SERVER_BIN: str = "llama-server"
    LOCAL_LLM_MODEL_PATH: str = "/app/models/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf"
    LOCAL_LLM_MODEL_NAME: str = "Qwen3-4B-Instruct-2507"
    LOCAL_LLM_PORT: int = 8080
    LOCAL_LLM_CTX: int = 8192
    LOCAL_LLM_GPU_LAYERS: int = 99
    LOCAL_LLM_PARALLEL: int = 2
    LOCAL_LLM_START_TIMEOUT: int = 120
    LOCAL_LLM_CHAT_TIMEOUT: int = 180

    # Model khusus tombol "Regenerate with AI" di popup klip (API/VPS).
    AI_REGENERATE_MODEL: Optional[str] = None
    # Batas regenerate per klip (dihitung dari tabel ai_regenerate_log).
    AI_REGENERATE_LIMIT: int = 3

    # Duitku Payment
    DUITKU_MERCHANT_CODE: Optional[str] = None
    DUITKU_API_KEY: Optional[str] = None
    DUITKU_CALLBACK_URL: Optional[str] = None
    DUITKU_RETURN_URL: Optional[str] = None
    DUITKU_SANDBOX: bool = True

    # Social Auth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    X_CLIENT_ID: Optional[str] = None
    X_CLIENT_SECRET: Optional[str] = None
    FACEBOOK_CLIENT_ID: Optional[str] = None
    FACEBOOK_CLIENT_SECRET: Optional[str] = None

    # Encryption
    ENCRYPTION_KEY: str

    # Video Processing
    MAX_VIDEO_DURATION_MINUTES: int = 120
    MAX_FILE_SIZE_MB: int = 2000
    OUTPUT_FPS: int = 30
    OUTPUT_RESOLUTION: str = "1080x1920"
    # Email yang otomatis punya akses admin dashboard (pisah koma).
    # Contoh: ADMIN_EMAILS=owner@clipzy.ai,partner@gmail.com
    ADMIN_EMAILS: str = ""

    # yt-dlp (download video dari YouTube/TikTok/IG/FB/Vimeo)
    # Cookies OPSIONAL. Isi salah satu saja:
    #   YTDLP_COOKIES_FILE   -> path file cookies.txt (format Netscape)
    #   YTDLP_COOKIES_BASE64 -> isi cookies.txt yang di-encode base64 (untuk Docker)
    # Kosong = download tanpa cookies (cukup untuk video publik dari IP residensial).
    YTDLP_COOKIES_FILE: Optional[str] = None
    YTDLP_COOKIES_BASE64: Optional[str] = None
    # Lokasi hasil decode base64 (dibuat otomatis saat runtime).
    YTDLP_COOKIES_CACHE_PATH: Optional[str] = None
    # Proxy opsional untuk melewati blokir IP datacenter, mis. http://user:pass@host:port
    YTDLP_PROXY: Optional[str] = None
    # Opsional, mis. "youtube:player_client=web_safari,android"
    YTDLP_EXTRACTOR_ARGS: Optional[str] = None

    # Rotasi cookies otomatis (tabel ytdlp_cookies)
    # Berapa kali gagal sebelum cookies ditandai expired
    YTDLP_COOKIE_MAX_FAILURES: int = 3
    # Video probe untuk uji validitas cookies (harus video publik)
    YTDLP_COOKIE_PROBE_URL: str = "https://www.youtube.com/watch?v=BaW_jenozKc"
    # Folder cache file cookies (hasil decrypt). Kosong = ./.cache/ytdlp_cookies
    YTDLP_COOKIE_CACHE_DIR: Optional[str] = None

    # URL API yang dipakai frontend. Tidak dipakai backend, tetapi dibaca di sini
    # agar satu file .env bisa dipakai bersama (Docker compose) tanpa error
    # "extra inputs are not permitted".
    NEXT_PUBLIC_API_URL: Optional[str] = None

    # Deployment hybrid: Vast.ai Serverless (worker GPU untuk proses video)
    VAST_API_KEY: Optional[str] = None
    VAST_ENDPOINT_NAME: str = "clipzi-processing"
    # ID resource yang dikelola `scripts/vastai-setup.py` (status/retemplate/update).
    # Tidak dipakai API saat runtime, tetapi dibaca di sini supaya satu .env bisa
    # dipakai bersama skrip & container tanpa error "extra inputs are not permitted".
    VAST_ENDPOINT_ID: Optional[int] = None
    VAST_WORKERGROUP_ID: Optional[int] = None
    VAST_TEMPLATE_HASH: Optional[str] = None
    VAST_TEMPLATE_NAME: str = "clipzi-worker"
    VAST_TEMPLATE_PUBLIC: bool = False
    VAST_WORKER_IMAGE: Optional[str] = None
    VAST_WORKER_DISK: int = 40
    VAST_WORKER_ONSTART: Optional[str] = None
    VAST_GPU_FILTER: str = "gpu_ram>=16 disk_space>=40 inet_down>200"
    VAST_MIN_WORKERS: int = 0
    VAST_MAX_WORKERS: int = 4
    VAST_TARGET_UTIL: float = 0.9
    VAST_INACTIVITY_TIMEOUT: int = 300
    # Mode dispatch (lihat app/services/vast_worker.py):
    #   VAST_ENDPOINT_URL  -> POST langsung ke URL endpoint (paling portabel)
    #   kosong             -> pakai SDK `vastai` (Serverless.queue_endpoint_request)
    VAST_ENDPOINT_URL: Optional[str] = None
    # Timeout tunggu respons worker (detik) untuk mode HTTP
    VAST_REQUEST_TIMEOUT: int = 600
    # Port worker HTTP (dipakai deployments/worker_api.py)
    WORKER_PORT: int = 8000
    # Folder kerja sementara untuk unduh/render di worker
    WORKER_WORK_DIR: str = "./work"

    # Paksa mode dispatch: http | sdk | oneshot | inline.
    # Kosong = otomatis (http kalau ada URL, lalu sdk, lalu inline).
    VAST_DISPATCH_MODE: Optional[str] = None
    # Mode `oneshot`: satu instance dibuat per task lalu DIHAPUS setelah selesai.
    # Membutuhkan VAST_API_KEY + VAST_WORKER_IMAGE (atau VAST_TEMPLATE_HASH) dan
    # secret pipeline sudah diset sebagai Environment Variables akun Vast.
    VAST_ONESHOT_MAX_PRICE: float = 0.0     # 0 = tanpa batas harga ($/jam)
    VAST_ONESHOT_TIMEOUT: int = 3600        # detik sebelum instance dipaksa dihapus
    VAST_ONESHOT_BOOT_TIMEOUT: int = 900    # detik menunggu worker mulai memproses
    VAST_ONESHOT_REAP_INTERVAL: int = 20    # detik antar polling status task

    # ---------- Supervisor instance (auto-replace saat boot gagal) ----------
    # Kebijakan agresif: 5 percobaan, backoff 5 s, harga offer boleh naik 2×.
    VAST_MAX_ATTEMPTS: int = 5
    VAST_RETRY_BACKOFF: int = 5
    VAST_MAX_PRICE_MULTIPLIER: float = 2.0
    VAST_BOOT_TIMEOUT: int = 420            # image pull ±5 GB; instance harus running dalam waktu ini
    VAST_WORKER_START_TIMEOUT: int = 120    # task harus mulai diproses setelah running
    VAST_SUPERVISOR_INTERVAL: int = 5       # detik antar polling status instance

    # Callback worker → API (webhook milik kita; Vast tidak menyediakan webhook).
    CLIPZI_WORKER_TOKEN: Optional[str] = None
    CLIPZI_CALLBACK_URL: Optional[str] = None

    # Unggah bundle log worker (worker.log + llama-server.log + env) ke qurl.sh
    # di akhir setiap task, supaya bisa dianalisis walau instance sudah dihapus.
    WORKER_LOG_UPLOAD: bool = True

    # Email SMTP
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@clipzi.ai"

    # CORS - comma-separated string from .env
    CORS_ORIGINS_RAW: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return [item.strip() for item in self.CORS_ORIGINS_RAW.split(",") if item.strip()]

    @field_validator("DATABASE_URL")
    @classmethod
    def _use_async_driver(cls, value: str) -> str:
        """Paksa driver async (asyncpg) untuk SQLAlchemy.

        Connection string dari Supabase/Neon biasanya berbentuk
        `postgres://` atau `postgresql://` (driver sync). Tanpa normalisasi ini
        `create_async_engine` gagal saat start karena mencoba memuat psycopg2.
        """
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value[len("postgres://"):]
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value[len("postgresql://"):]
        return value

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    # Nilai wajib dibaca dari environment/.env saat runtime, sehingga Pylance
    # tidak bisa memverifikasi argumen konstruktor di sini.
    return Settings()  # type: ignore[call-arg]