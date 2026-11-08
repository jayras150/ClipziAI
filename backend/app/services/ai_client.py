"""
AI Provider Client - OpenAI-compatible client for any provider.

Clipzi AI supports ANY provider that exposes an OpenAI-compatible chat
completions API. Configure everything through environment variables:

    AI_PROVIDER  = openai | groq | openrouter | together | deepseek
                   | mistral | azure | ollama | custom
    AI_API_KEY   = the API key / token for the chosen provider
    AI_BASE_URL  = optional; provider default is used when omitted
    AI_MODEL     = optional; provider default model is used when omitted
    AI_TEMPERATURE = 0.0 - 1.0 (default 0.7)
    AI_MAX_TOKENS  = max completion tokens (default 2048)

Legacy fallbacks (still supported, so existing .env files keep working):
    OPENAI_API_KEY is used when AI_API_KEY is not set.

Examples:
    # OpenAI
    AI_PROVIDER=openai
    AI_API_KEY=sk-...
    AI_MODEL=gpt-4o-mini

    # Groq (fast, free tier)
    AI_PROVIDER=groq
    AI_API_KEY=gsk_...

    # OpenRouter (one key, many models)
    AI_PROVIDER=openrouter
    AI_API_KEY=sk-or-...
    AI_MODEL=openai/gpt-4o-mini

    # Ollama (local, no key needed)
    AI_PROVIDER=ollama
    AI_BASE_URL=http://localhost:11434/v1
    AI_MODEL=llama3.1
"""
from typing import Dict, Any, Optional

import openai

from app.core.config import get_settings

settings = get_settings()

# Provider -> default base URL + sensible default chat model.
# "custom" requires the user to set AI_BASE_URL and AI_MODEL explicitly.
PROVIDER_DEFAULTS: Dict[str, Dict[str, str]] = {
    "openai": {
        "base_url": "",
        "model": "gpt-4o-mini",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.1-8b-instant",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest",
    },
    "azure": {
        "base_url": "https://YOUR_RESOURCE.openai.azure.com/openai/v1/?api-version=2024-08-01-preview",
        "model": "",  # AI_MODEL must hold the deployment name for Azure
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.1",
    },
    "custom": {
        "base_url": "",
        "model": "",
    },
}


def get_ai_api_key() -> Optional[str]:
    """Return the active AI API key (AI_API_KEY, falling back to OPENAI_API_KEY)."""
    return settings.AI_API_KEY or settings.OPENAI_API_KEY


def get_ai_provider() -> str:
    """Normalised AI provider name (defaults to 'openai')."""
    provider = (settings.AI_PROVIDER or "openai").strip().lower()
    if provider not in PROVIDER_DEFAULTS:
        provider = "custom"
    return provider


def get_ai_base_url() -> Optional[str]:
    """Resolve the base URL for the configured provider (env override wins)."""
    provider = get_ai_provider()
    defaults: Dict[str, str] = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
    return settings.AI_BASE_URL or defaults.get("base_url") or None


def get_ai_model(default: Optional[str] = None) -> str:
    """Resolve the chat model for the configured provider."""
    provider = get_ai_provider()
    defaults: Dict[str, str] = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
    model = settings.AI_MODEL or defaults.get("model") or default
    return model or "gpt-4o-mini"


def get_ai_temperature() -> float:
    """Resolve the sampling temperature (default 0.7)."""
    return settings.AI_TEMPERATURE if settings.AI_TEMPERATURE is not None else 0.7


def get_ai_max_tokens() -> int:
    """Resolve the maximum completion tokens (default 2048)."""
    return settings.AI_MAX_TOKENS or 2048


def is_ai_configured() -> bool:
    """True when an API key is available (local providers may still work keyless)."""
    api_key = get_ai_api_key()
    base_url = get_ai_base_url()
    provider = get_ai_provider()
    if provider == "ollama":
        # Ollama/local endpoints usually don't need a key.
        return bool(base_url)
    return bool(api_key)


def get_ai_client() -> openai.AsyncOpenAI:
    """Build an OpenAI-compatible Async client for the configured provider."""
    api_key = get_ai_api_key() or "sk-no-key-provided"
    return openai.AsyncOpenAI(
        api_key=api_key,
        base_url=get_ai_base_url(),
        timeout=120.0,
        max_retries=2,
    )
