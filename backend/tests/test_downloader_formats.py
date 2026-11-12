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
    assert ladder[2] == "b"
    assert ladder[3] == "b*"
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
