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


def test_vast_error_text_tanpa_response():
    assert vast_worker._vast_error_text(RuntimeError("boom")) == "boom"
