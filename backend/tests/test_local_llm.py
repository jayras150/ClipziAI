"""Unit test LLM lokal (llama.cpp) + rerank kandidat klip."""
from __future__ import annotations

from typing import Any, Dict, List

from app.services.clip_planner import plan_clips, rerank_with_llm
from app.services.local_llm import LocalLLM, parse_json_object


class _FakeLLM:
    """LLM palsu: mengembalikan payload tetap tanpa memanggil server."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls = 0

    def chat_json(self, system: str, user: str, **kwargs: Any) -> Any:
        self.calls += 1
        return self.payload


def _candidates() -> List[Dict[str, Any]]:
    return [
        {
            "start": 10.0,
            "end": 80.0,
            "duration": 70.0,
            "score": 60.0,
            "factors": {"first_sentence": "Halo semuanya", "last_sentence": "Sampai jumpa"},
            "transcript": "halo semuanya sampai jumpa",
        },
        {
            "start": 200.0,
            "end": 270.0,
            "duration": 70.0,
            "score": 80.0,
            "factors": {"first_sentence": "Ini rahasianya", "last_sentence": "Itu intinya"},
            "transcript": "ini rahasianya itu intinya",
        },
    ]


def test_parse_json_object_membersihkan_code_fence():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object("jawaban: {\"b\": 2} selesai") == {"b": 2}
    assert parse_json_object("bukan json") is None
    assert parse_json_object("") is None


def test_rerank_menggabungkan_skor_llm_dan_heuristik():
    llm = _FakeLLM(
        {
            "clips": [
                {"id": 0, "score": 20, "hook": "Hook A", "reason": "lemah"},
                {"id": 1, "score": 100, "hook": "Hook B", "reason": "kuat"},
            ]
        }
    )
    result = rerank_with_llm(_candidates(), llm, 60, 90)

    assert llm.calls == 1
    # Shortlist diurutkan skor heuristik tertinggi dulu: id 0 = kandidat 80,
    # id 1 = kandidat 60.
    # 0.55*20 + 0.45*80 = 47.0 ; 0.55*100 + 0.45*60 = 82.0
    assert result[0]["score"] == 47.0
    assert result[0]["factors"]["llm_hook"] == "Hook A"
    assert result[1]["score"] == 82.0
    assert result[1]["factors"]["llm_reason"] == "kuat"
    assert result[1]["factors"]["llm_hook"] == "Hook B"
    assert result[1]["factors"]["reranked_by"].startswith("qwen3")


def test_rerank_tanpa_payload_valid_tidak_mengubah_skor():
    original = _candidates()
    assert rerank_with_llm(original, _FakeLLM(None), 60, 90) == original
    assert rerank_with_llm(original, _FakeLLM({"clips": "salah"}), 60, 90) == original
    assert rerank_with_llm(original, None, 60, 90) == original


def test_plan_clips_memakai_llm_untuk_memilih_momen():
    segments: List[Dict[str, Any]] = []
    cursor = 0.0
    for index in range(80):
        words = []
        for word_index in range(12):
            text = f"kata{index}x{word_index}" + ("." if word_index == 11 else "")
            words.append(
                {"word": text, "start": round(cursor, 3), "end": round(cursor + 0.38, 3)}
            )
            cursor += 0.38
        segments.append(
            {"start": words[0]["start"], "end": words[-1]["end"], "text": " ".join(w["word"] for w in words), "words": words}
        )
        cursor += 0.6

    llm = _FakeLLM({"clips": [{"id": 0, "score": 10, "hook": "x", "reason": "y"}]})
    clips = plan_clips(segments, [], cursor, 60, 90, 2, llm=llm)
    assert clips, "planner harus tetap menghasilkan klip saat LLM aktif"
    assert llm.calls == 1


def test_local_llm_nonaktif_tanpa_binary(monkeypatch):
    from app.services import local_llm as module

    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    llm = LocalLLM()
    assert llm.available is False
    assert llm.start() is False
    assert llm.chat_json("s", "u") is None
