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


class _Collect:
    def __init__(self):
        self.items = []

    def put_nowait(self, item):
        self.items.append(item)


def test_progres_download_spam_dibuang(monkeypatch):
    """Baris '[download] 75.2% of ...' tidak boleh masuk log admin."""
    from deployments import worker_log_shipper as shipper

    sink = _Collect()
    monkeypatch.setattr(shipper, "BUFFER", sink, raising=False)
    monkeypatch.setattr(
        shipper, "PROGRESS_STATE", {"text": "", "done": False}, raising=False
    )

    shipper.emit("[download]  75.2% of ~   1.43GiB at    5.88MiB/s ETA 01:07 (frag 470/626)")
    shipper.emit("[download]  75.3% of ~   1.43GiB at    5.95MiB/s ETA 01:06 (frag 470/626)")

    assert sink.items == [], "spam progres harus dibuang"

    shipper.emit("[download] 100.0% of ~1.43GiB at 6.00MiB/s ETA 00:00")
    assert len(sink.items) == 1
    assert "download selesai" in sink.items[0]["message"]


def test_baris_download_penting_tetap_dikirim(monkeypatch):
    from deployments import worker_log_shipper as shipper

    sink = _Collect()
    monkeypatch.setattr(shipper, "BUFFER", sink, raising=False)

    shipper.emit("[download] Destination: /tmp/source.mp4")

    assert len(sink.items) == 1
    assert "Destination" in sink.items[0]["message"]


def test_backend_filter_progres_download():
    from app.services import worker_log_lines as lines

    match = lines._DOWNLOAD_PROGRESS.match(
        "[download]  75.2% of ~   1.43GiB at    5.88MiB/s ETA 01:07"
    )
    assert match is not None
    assert float(match.group(1)) == 75.2
    assert lines._DOWNLOAD_PROGRESS.match("[download] Destination: /tmp/a.mp4") is None
