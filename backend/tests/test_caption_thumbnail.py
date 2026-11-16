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
