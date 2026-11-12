"""Regression test adapter provider untuk planner (sinkron + deadline)."""
import time

from app.services import ai_config
from app.services.provider_llm import ProviderJSONClient


def _cfg(**extra):
    payload = {
        "provider": "openrouter",
        "api_key_enc": ai_config.encrypt_api_key("sk-or-test-123456"),
        "temperature": 0.2,
        "timeout_seconds": 30,
        "max_retries": 0,
    }
    payload.update(extra)
    return ai_config.normalize_ai(payload)


def test_chat_json_any_memakai_model_dan_endpoint_dari_config(monkeypatch):
    captured = {}

    class _Message:
        content = '{"clips": [{"id": 0, "score": 90}]}'

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = _Chat()

    monkeypatch.setattr("app.services.provider_llm.openai.OpenAI", _Client)

    client = ProviderJSONClient(_cfg(), "openai/gpt-4o")
    payload = client.chat_json_any("sistem", "user", max_tokens=300)

    assert payload == {"clips": [{"id": 0, "score": 90}]}
    assert captured["model"] == "openai/gpt-4o"
    assert captured["client"]["api_key"] == "sk-or-test-123456"
    assert captured["client"]["base_url"] == "https://openrouter.ai/api/v1"


def test_deadline_habis_tidak_memanggil_provider(monkeypatch):
    def _boom(**kwargs):
        raise AssertionError("provider tidak boleh dipanggil")

    monkeypatch.setattr("app.services.provider_llm.openai.OpenAI", _boom)
    client = ProviderJSONClient(_cfg(), "openai/gpt-4o")
    assert client.chat_json_any("s", "u", deadline=time.monotonic() - 1) is None
    assert "anggaran waktu" in client.last_error


def test_error_provider_dicatat_tanpa_exception(monkeypatch):
    class _Client:
        def __init__(self, **kwargs):
            class _Chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        raise RuntimeError("401 Unauthorized")

            self.chat = _Chat()

    monkeypatch.setattr("app.services.provider_llm.openai.OpenAI", _Client)
    client = ProviderJSONClient(_cfg(), "openai/gpt-4o")
    assert client.chat_json_any("s", "u") is None
    assert "401" in client.last_error
