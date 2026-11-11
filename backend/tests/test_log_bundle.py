"""Unit test bundle log worker (qurl.sh) — tanpa jaringan."""
from __future__ import annotations

import os
import tarfile

from app.services import log_bundle


def test_parse_url_mengambil_url_file_bukan_qr():
    text = (
        "\u2714 Success - uploaded clipzi-logs.tar.gz (12 KB)\n"
        "QR Code: https://qurl.sh/qr/abcd/clipzi-logs.tar.gz\n"
        "https://qurl.sh/abcd/clipzi-logs.tar.gz\n"
    )
    assert log_bundle._parse_url(text) == "https://qurl.sh/abcd/clipzi-logs.tar.gz"


def test_parse_url_tanpa_url_mengembalikan_none():
    assert log_bundle._parse_url("gagal upload") is None


def test_build_bundle_membuat_tar_gz(tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "clip_01.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhalo\n")

    bundle, error = log_bundle._build_bundle("12345678-0000", str(work_dir))
    assert bundle and os.path.exists(bundle), error
    with tarfile.open(bundle, "r:gz") as tar:
        names = tar.getnames()
    assert any(name.startswith("work-clip_01.srt") for name in names)
    os.remove(bundle)
