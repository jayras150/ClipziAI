"""Regresi: budget token metadata untuk reasoning model.

Bukti produksi (task 7aadafab, 2026-11-20):
  ``deepseek-v4-pro`` dengan ``max_tokens=900`` menghabiskan 900/900 token
  untuk reasoning → ``content`` kosong, ``finish_reason=length``.
  ``deepseek-flash`` kadang sama (content terpotong sebelum JSON) →
  "AI response is not JSON." / "AI returned an empty response."
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.services.metadata_generator import (
    DEFAULT_METADATA_MAX_TOKENS,
    MAX_METADATA_MAX_TOKENS,
    MetadataGenerator,
    _metadata_max_tokens,
)

TRANSCRIPT = (
    "jadi gini guys saya mau kasih tips budgeting yang benar buat anak muda "
    "supaya gaji tidak habis sebelum akhir bulan dan bisa mulai nabung "
    "sisihkan tabungan di awal lalu atur pengeluaran harian dengan batas jelas"
)

PAYLOAD = {
    "title": "Budgeting Rule That Saved 40% of My Salary",
    "description": (
        "Sisihkan tabungan di awal, bukan di akhir. Pola 50/30/20 gagal karena "
        "urutan transfernya salah. #budgeting #nabung"
    ),
    "tags": ["budgeting", "nabung", "gaji", "keuangan", "tips", "anak muda"],
    "hook": "Gaji habis sebelum akhir bulan?",
    "viral_reason": "Angka 40% membuat klaim konkret dan mudah dipercaya.",
    "language": "id",
}


def _response(content: str, finish: str = "stop", reasoning: int = 0):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish,
            )
        ],
        usage=SimpleNamespace(
            completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning)
        ),
    )


class _Completions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _Client:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=_Completions(responses))


def test_budget_naik_dan_pulih_saat_reasoning_habis():
    client = _Client(
        [
            _response("", finish="length", reasoning=4096),
            _response(json.dumps(PAYLOAD), reasoning=200),
        ]
    )
    generator = MetadataGenerator(client=client, model="deepseek-v4-pro", max_tokens=4096)

    result = asyncio.run(generator.generate(transcript=TRANSCRIPT, duration=42))

    calls = client.chat.completions.calls
    assert calls[0]["max_tokens"] == 4096
    assert calls[1]["max_tokens"] == 8192, "percobaan 2 harus naik 2× lipat"
    assert result["title"] == PAYLOAD["title"]


def test_budget_dibatasi_maksimum():
    client = _Client([_response("", finish="length"), _response("", finish="length")])
    generator = MetadataGenerator(client=client, model="m", max_tokens=12000)

    try:
        asyncio.run(generator.generate(transcript=TRANSCRIPT, duration=42))
    except Exception:  # noqa: BLE001 - semua percobaan memang gagal
        pass

    budgets = [call["max_tokens"] for call in client.chat.completions.calls]
    assert budgets[:2] == [12000, MAX_METADATA_MAX_TOKENS]
    assert all(budget <= MAX_METADATA_MAX_TOKENS for budget in budgets)


def test_default_dan_env_max_tokens(monkeypatch):
    monkeypatch.delenv("METADATA_MAX_TOKENS", raising=False)
    assert _metadata_max_tokens() == DEFAULT_METADATA_MAX_TOKENS
    assert DEFAULT_METADATA_MAX_TOKENS >= 4096

    monkeypatch.setenv("METADATA_MAX_TOKENS", "600")
    assert _metadata_max_tokens() == 600

    monkeypatch.setenv("METADATA_MAX_TOKENS", "99999")
    assert _metadata_max_tokens() == MAX_METADATA_MAX_TOKENS

    monkeypatch.setenv("METADATA_MAX_TOKENS", "bukan-angka")
    assert _metadata_max_tokens() == DEFAULT_METADATA_MAX_TOKENS
