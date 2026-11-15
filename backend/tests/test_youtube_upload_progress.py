"""Progress upload YouTube: file wrapper harus melaporkan 0-100% dengan benar."""
from types import SimpleNamespace

from app.services import youtube_service
from app.services.youtube_service import _ProgressFile, YouTubeService


def test_progress_file_reports_chunk_progress(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 1000)
    events: list[tuple[int, int, int]] = []
    handle = _ProgressFile(
        str(path),
        1000,
        lambda percent, sent, total: events.append((percent, sent, total)),
        base_percent=40,
        span_percent=59,
    )
    try:
        assert handle.read(500)
        assert handle.read(500)
        assert handle.read(1) == b""
    finally:
        handle.close()
    assert events[0] == (69, 500, 1000)
    assert events[-1] == (99, 1000, 1000)


def test_progress_callback_error_does_not_break_upload(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 10)

    def broken(percent: int, sent: int, total: int) -> None:
        raise RuntimeError("ui error")

    handle = _ProgressFile(str(path), 10, broken)
    try:
        assert handle.read(10) == b"x" * 10
    finally:
        handle.close()


def test_upload_sync_emits_progress_and_finishes_at_100(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 2048)
    events: list[tuple[int, int, int]] = []

    def fake_post(*args, **kwargs):
        return SimpleNamespace(ok=True, status_code=200, headers={"Location": "https://upload.test"})

    def fake_put(*args, data=None, **kwargs):
        body = data
        assert body is not None
        while body.read(512):
            pass
        return SimpleNamespace(status_code=200, json=lambda: {"id": "video-123"})

    monkeypatch.setattr(youtube_service.requests, "post", fake_post)
    monkeypatch.setattr(youtube_service.requests, "put", fake_put)
    result = YouTubeService()._upload_sync(
        "token",
        str(path),
        "Title",
        "Description",
        [],
        "unlisted",
        "22",
        False,
        None,
        None,
        lambda percent, sent, total: events.append((percent, sent, total)),
    )
    assert result["video_id"] == "video-123"
    assert events[0][0] == 1
    assert events[-1][0] == 100
    assert events[-1][1] == 2048
    assert events[-1][2] == 2048
