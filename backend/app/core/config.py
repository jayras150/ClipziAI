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

    # AI Provider (any OpenAI-compatible LLM provider)
    # Provider: openai | groq | openrouter | together | deepseek | mistral | azure | ollama | custom
    AI_PROVIDER: str = "openai"
    AI_API_KEY: Optional[str] = None          # if AI_API_KEY is empty, falls back to OPENAI_API_KEY
    AI_BASE_URL: Optional[str] = None         # optional; provider default used when omitted
    AI_MODEL: Optional[str] = None            # optional; provider default model used when omitted
    AI_TEMPERATURE: float = 0.7
    AI_MAX_TOKENS: int = 2048

    # Audio transcription provider
    # Provider: local | openai | groq | together | custom
    # Non-local providers must expose the OpenAI-compatible /audio/transcriptions API.
    TRANSCRIPTION_PROVIDER: str = "local"
    TRANSCRIPTION_API_KEY: Optional[str] = None
    TRANSCRIPTION_BASE_URL: Optional[str] = None
    TRANSCRIPTION_MODEL: Optional[str] = None

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
    return Settings()