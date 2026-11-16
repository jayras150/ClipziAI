"""Tes penanganan offer Vast yang sudah tidak tersedia (400 create_instance)."""
from app.services import vast_worker


class _FakeResponse:
    status_code = 400
    text = '{"success": false, "error": "ask 28852193 not found"}'


class _FakeError(Exception):
    response = _FakeResponse()


def test_vast_error_text_mengambil_body():
    text = vast_worker._vast_error_text(_FakeError())
    assert "HTTP 400" in text
    assert "ask 28852193 not found" in text


def test_stale_offer_error_mengenali_ask_hilang():
    assert vast_worker._stale_offer_error("HTTP 400: ask 1 not found")
    assert vast_worker._stale_offer_error("The resource could not be found")
    assert vast_worker._stale_offer_error("offer is no longer available")
    assert not vast_worker._stale_offer_error("image not permitted for this user")


def test_template_invalid_beralih_ke_image(monkeypatch):
    """Template hash tersimpan bisa tidak valid; dispatch harus pakai image."""
    import asyncio
    from uuid import UUID

    import requests as _requests

    from app.services import vast_worker

    calls = []

    class _Resp:
        status_code = 400
        text = '{"success":false,"error":"invalid_args","msg":"invalid template hash or id"}'
        ok = False

    def fake_post(offer_id, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise _requests.HTTPError("400 Client Error", response=_Resp())
        return {"success": True, "new_contract": 777}

    monkeypatch.setattr(vast_worker, "_post_create_instance", fake_post)
    monkeypatch.setattr(vast_worker.settings, "VAST_WORKER_IMAGE", "user/img:worker")
    monkeypatch.setattr(vast_worker.settings, "VAST_TEMPLATE_HASH", "hash-lama")
    monkeypatch.setattr(vast_worker.settings, "CLIPZI_CALLBACK_URL", "https://x/api/internal/worker/events")
    monkeypatch.setattr(vast_worker.settings, "CLIPZI_WORKER_TOKEN", "tok")

    create = vast_worker._make_create_instance(
        UUID("00000000-0000-0000-0000-000000000003"), object()
    )
    assert asyncio.run(create({"id": 99})) == 777
    assert calls[0]["template_hash"] == "hash-lama"
    assert calls[1]["template_hash"] == ""
    assert calls[1]["image"] == "user/img:worker"

