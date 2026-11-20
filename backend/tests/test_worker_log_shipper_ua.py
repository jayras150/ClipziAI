"""Regresi: shipper log worker HARUS mengirim User-Agent sendiri.

Cloudflare memblokir User-Agent default urllib (`Python-urllib/3.11`) dengan
"error code: 1010" / HTTP 403. Dulu shipper tidak mengirim UA sehingga SEMUA
log pipeline ditolak backend, dan admin hanya melihat log boot dari
onstart_log.py. Terbukti di produksi: UA urllib -> 403, UA ClipziAI -> 200.
"""
from __future__ import annotations


def test_post_mengirim_user_agent(monkeypatch):
    from deployments import worker_log_shipper as shipper

    captured = {}

    class DummyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=15):
        captured["ua"] = request.headers.get("User-agent")
        captured["url"] = request.full_url
        return DummyResponse()

    monkeypatch.setattr(shipper.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(shipper, "API", "https://example.test", raising=False)
    monkeypatch.setattr(shipper, "TOKEN", "tok", raising=False)

    ok = shipper._post(
        [{"seq": 1, "level": "INFO", "stage": "boot", "message": "halo"}]
    )

    assert ok is True
    assert captured["ua"] == shipper.USER_AGENT
    assert captured["ua"] != "Python-urllib/3.11"
    assert captured["url"].endswith("/api/internal/worker/logs")


def test_post_tanpa_baris_tidak_memanggil_http(monkeypatch):
    from deployments import worker_log_shipper as shipper

    called = {"n": 0}

    def fake_urlopen(request, timeout=15):  # pragma: no cover
        called["n"] += 1
        raise AssertionError("tidak boleh memanggil HTTP tanpa baris")

    monkeypatch.setattr(shipper.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(shipper, "API", "https://example.test", raising=False)
    monkeypatch.setattr(shipper, "TOKEN", "tok", raising=False)

    assert shipper._post([]) is False
    assert called["n"] == 0


def test_batas_pesan_20000():
    from deployments import worker_log_shipper as shipper
    import inspect

    source = inspect.getsource(shipper.emit)
    assert "20000" in source
