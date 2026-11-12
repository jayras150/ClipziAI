"""
Adapter provider AI (OpenAI-compatible) untuk `clip_planner.rerank_with_llm`.

Planner bersifat sinkron dan sudah dijalankan di executor, jadi adapter ini juga
sinkron. Deadline dihormati dengan memotong `timeout` sesuai sisa waktu.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import openai

from app.services.ai_config import decrypt_api_key, effective_base_url
from app.services.local_llm import parse_json_any

logger = logging.getLogger(__name__)


class ProviderJSONClient:
    """Klien JSON sinkron untuk provider AI (dipakai di thread executor)."""

    def __init__(self, cfg: Dict[str, Any], model: str) -> None:
        self.model = model
        self.base_url = effective_base_url(cfg)
        self.api_key = decrypt_api_key(cfg.get("api_key_enc")) or "sk-no-key-provided"
        self.temperature = float(cfg.get("temperature") or 0.2)
        self.timeout = float(cfg.get("timeout_seconds") or 90)
        self.max_retries = int(cfg.get("max_retries") or 1)
        self.last_error = ""

    def chat_json_any(
        self,
        system: str,
        user: str,
        max_tokens: int = 300,
        temperature: Optional[float] = None,
        deadline: Optional[float] = None,
    ) -> Any:
        timeout = self.timeout
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 2:
                self.last_error = "anggaran waktu AI habis sebelum panggilan"
                return None
            timeout = min(timeout, max(2.0, remaining))
        client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
            max_retries=self.max_retries,
        )
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature if temperature is None else temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            payload = parse_json_any(content)
            if payload is None:
                self.last_error = "balasan provider bukan JSON valid"
            return payload
        except Exception as exc:
            self.last_error = (type(exc).__name__ + ": " + str(exc))[:300]
            logger.warning("Provider AI gagal menjawab: %s", self.last_error)
            return None
