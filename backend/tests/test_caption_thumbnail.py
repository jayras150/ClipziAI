"""Tes katalog 50 style caption thumbnail + renderer + watermark default."""
from __future__ import annotations

import io

from PIL import Image

from app.services import thumbnail_render
from app.services.caption_catalog import CAPTION_STYLES
from app.services.platform_settings import DEFAULT_WATERMARK


def test_katalog_50_style_unik():
    assert len(CAPTION_STYLES) == 50
    assert len(set(CAPTION_STYLES)) == 50
    for key, value in CAPTION_STYLES.items():
        assert key
        assert value["label"]
        assert value["size"] > 0


def test_anchor_sembilan_posisi():
    assert len(thumbnail_render.ANCHORS) == 9
    assert "bottom-center" in thumbnail_render.ANCHORS
    assert "top-left" in thumbnail_render.ANCHORS


def _frame() -> bytes:
    image = Image.new("RGB", (1280, 720), (25, 32, 48))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _portrait_frame() -> bytes:
    image = Image.new("RGB", (720, 1280), (44, 22, 70))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_target_size_mengikuti_rasio():
    assert thumbnail_render.target_size((1920, 1080)) == (1280, 720)
    assert thumbnail_render.target_size((1080, 1920)) == (1080, 1920)
    assert thumbnail_render.target_size((720, 1280)) == (1080, 1920)
    assert thumbnail_render.target_size((1080, 1080)) == (1280, 1280)


def test_portrait_9_16_tidak_digepengkan():
    output = thumbnail_render.render_caption_thumbnail(
        _portrait_frame(), "Viral portrait clip", "hormozi-pop", "bottom-center"
    )
    image = Image.open(io.BytesIO(output))
    assert image.size == (1080, 1920)
    assert abs(image.size[0] / image.size[1] - 9 / 16) < 0.01
    assert image.format == "JPEG"


def test_to_landscape_untuk_youtube():
    output = thumbnail_render.to_landscape(_portrait_frame())
    image = Image.open(io.BytesIO(output))
    assert image.size == (1280, 720)
    assert len(output) <= 2_000_000


def test_render_menghasilkan_jpeg_1280x720():
    for style in ("acid-lime", "holo-chrome", "minimal-badge"):
        output = thumbnail_render.render_caption_thumbnail(
            _frame(), "This is a viral moment", style, "top-left"
        )
        image = Image.open(io.BytesIO(output))
        assert image.size == (1280, 720)
        assert image.format == "JPEG"
        assert len(output) > 3000


def test_render_semua_anchor_tidak_error():
    for anchor in thumbnail_render.ANCHORS:
        output = thumbnail_render.render_caption_thumbnail(
            _frame(), "Caption", "hormozi-pop", anchor
        )
        assert output


def test_style_options_kirim_50():
    options = thumbnail_render.style_options()
    assert len(options) == 50
    assert {"id", "label", "position"} <= set(options[0])


def test_watermark_default_top_left():
    assert DEFAULT_WATERMARK["position"] == "top-left"


def test_set_thumbnail_youtube(monkeypatch):
    from app.services import youtube_service as ys

    calls = {}

    class _Resp:
        status_code = 200
        content = b"jpegdata"
        ok = True

    def fake_get(url, headers=None, timeout=None):
        calls["get"] = url
        return _Resp()

    def fake_post(url, params=None, headers=None, data=None, timeout=None):
        calls["post"] = (url, params, data)
        return _Resp()

    monkeypatch.setattr(ys.requests, "get", fake_get)
    monkeypatch.setattr(ys.requests, "post", fake_post)

    ys.YouTubeService._set_thumbnail("token", "abc123", "https://files.example/thumb.jpg")
    assert calls["get"] == "https://files.example/thumb.jpg"
    url, params, data = calls["post"]
    assert url.endswith("/thumbnails/set")
    assert params["videoId"] == "abc123"
    assert data == b"jpegdata"


def test_pick_clean_frame_pilih_terdekat():
    frames = [
        {"at_second": 1.0, "url": "https://x/1.jpg"},
        {"at_second": 5.0, "url": "https://x/5.jpg"},
        {"at_second": 9.0, "url": "https://x/9.jpg"},
    ]
    assert thumbnail_render.pick_clean_frame(frames, 4.2) == (5.0, "https://x/5.jpg")
    assert thumbnail_render.pick_clean_frame(frames, 8.1) == (9.0, "https://x/9.jpg")
    assert thumbnail_render.pick_clean_frame([], 1.0) is None
    assert thumbnail_render.pick_clean_frame(None, 1.0) is None
    assert thumbnail_render.pick_clean_frame([{"at_second": 1}], 1.0) is None


def test_candidate_thumbnail_pakai_frame_bersih():
    from app.api.clips import _clean_candidates

    frames = [
        {"at_second": 3.0, "url": "https://x/a.jpg"},
        {"at_second": 30.0, "url": "https://x/b.jpg"},
        {"at_second": 55.0, "url": "https://x/c.jpg"},
    ]
    picked = _clean_candidates(frames, [9.0, 30.0, 51.0])
    assert [item.url for item in picked] == ["https://x/a.jpg", "https://x/b.jpg", "https://x/c.jpg"]
    assert _clean_candidates([], [1.0, 2.0, 3.0]) == []


def test_set_thumbnail_error_dilaporkan(monkeypatch):
    from app.services import youtube_service as ys

    class _Resp:
        status_code = 200
        content = b"jpegdata"
        ok = False
        text = '{"error":{"code":403,"message":"no permission"}}'
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {"error": {"code": 403, "message": "no permission", "errors": [{"reason": "forbidden"}]}}

    monkeypatch.setattr(ys.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(ys.requests, "post", lambda *a, **k: _Resp())
    result = ys.YouTubeService._set_thumbnail("token", "abc", "https://files/x.jpg")
    assert result["ok"] is False
    assert "no permission" in str(result["error"])


_SRT_CONTOH = """1
00:00:00,000 --> 00:00:02,000
Halo semua

2
00:00:04,000 --> 00:00:10,000
Ini klip viral
"""


def test_subtitle_free_second_pilih_jeda():
    from app.api.clips import subtitle_free_second

    assert subtitle_free_second(_SRT_CONTOH, 10.0, 3.0) == 3.0
    assert subtitle_free_second(_SRT_CONTOH, 10.0, 1.0) == 3.0
    assert subtitle_free_second(_SRT_CONTOH, 10.0, 9.0) == 3.0
    assert subtitle_free_second("", 10.0, 3.0) is None
    assert subtitle_free_second(_SRT_CONTOH, 0.0, 1.0) is None


def test_subtitle_free_second_tanpa_jeda():
    from app.api.clips import subtitle_free_second

    penuh = "\n".join(["1", "00:00:00,000 --> 00:00:10,000", "Penuh", ""])
    assert subtitle_free_second(penuh, 10.0, 4.0) is None
