"""
Test untuk format ladder yt-dlp (fix "Requested format is not available").

Pure unit, tanpa jaringan: hanya memastikan urutan selector & batas resolusi
sesuai rencana sehingga worker selalu punya fallback.
"""


def test_format_ladder_urutan_dan_batas():
    from app.services.downloader import format_ladder

    ladder = format_ladder(720)
    assert ladder[0].startswith("bv*[height<=720]+ba/b[height<=720]/b")
    assert ladder[1] == "bv*+ba/b"
    # fallback eksplisit ala yt-dlp manual (mp4/m4a) lalu format gabungan 360p
    assert ladder[2] == "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    assert ladder[3] == "18"
    assert ladder[4] == "b"
    assert ladder[5] == "b*"
    # `bv*` wajib: menerima format gabungan (video+audio) juga.
    assert ladder[0].count("bv*") == 1


def test_format_ladder_clamp_dan_nilai_aneh():
    from app.services.downloader import format_ladder

    assert "height<=2160" in format_ladder(9999)[0]
    assert "height<=144" in format_ladder(1)[0]
    assert "height<=720" in format_ladder("bukan-angka")[0]  # type: ignore[arg-type]
    assert "height<=720" in format_ladder(None)[0]  # type: ignore[arg-type]


def test_client_ladder_dimulai_default():
    from app.services.downloader import CLIENT_LADDER

    assert CLIENT_LADDER[0] is None
    assert ["web"] in CLIENT_LADDER
    assert any("android" in (entry or []) for entry in CLIENT_LADDER)


def test_ytdlp_version_terbaca():
    from app.services.downloader import ytdlp_version

    version = ytdlp_version()
    assert isinstance(version, str) and version
    assert version != ""


def test_deteksi_bot_check():
    from app.services.downloader import looks_like_bot_check

    assert looks_like_bot_check("ERROR: Sign in to confirm you are not a bot")
    assert looks_like_bot_check("please sign in to confirm you are not a bot")
    assert not looks_like_bot_check("Requested format is not available")
    assert not looks_like_bot_check("")


def _downloader():
    from app.services.downloader import VideoDownloader

    return VideoDownloader.__new__(VideoDownloader)


def test_pick_auto_format_pilih_tertinggi_maks_1080():
    dl = _downloader()
    formats = [
        {"format_id": "sb0", "ext": "mhtml", "height": 180, "vcodec": "none", "acodec": "none"},
        {"format_id": "140", "ext": "m4a", "height": None, "vcodec": "none", "acodec": "mp4a.40.2", "tbr": 129},
        {"format_id": "137", "ext": "mp4", "height": 1080, "vcodec": "avc1.640028", "acodec": "none", "tbr": 2818},
        {"format_id": "136", "ext": "mp4", "height": 720, "vcodec": "avc1.64001F", "acodec": "none", "tbr": 1420},
        {"format_id": "4000", "ext": "mp4", "height": 2160, "vcodec": "av01.0.12M", "acodec": "none", "tbr": 9000},
    ]
    candidates, videos = dl._pick_auto_format(formats)

    assert candidates[0] == "137+140"
    assert "best[height<=1080]" in candidates
    assert all((video.get("height") or 0) <= 1080 for video in videos)


def test_pick_auto_format_storyboard_only():
    dl = _downloader()
    formats = [
        {"format_id": "sb0", "ext": "mhtml", "height": 180, "vcodec": "none", "acodec": "none"},
        {"format_id": "sb1", "ext": "mhtml", "height": 90, "vcodec": "none", "acodec": "none"},
    ]
    candidates, videos = dl._pick_auto_format(formats)

    assert candidates == []
    assert videos == []


def test_pick_auto_format_progresif_dipakai_langsung():
    dl = _downloader()
    formats = [
        {"format_id": "18", "ext": "mp4", "height": 360, "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "tbr": 459},
        {"format_id": "137", "ext": "mp4", "height": 1080, "vcodec": "avc1.640028", "acodec": "none", "tbr": 2818},
        {"format_id": "140", "ext": "m4a", "height": None, "vcodec": "none", "acodec": "mp4a.40.2", "tbr": 129},
    ]
    candidates, videos = dl._pick_auto_format(formats)

    assert candidates[0] == "137+140"
    assert videos[0]["format_id"] == "137"
