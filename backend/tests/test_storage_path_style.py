"""Regresi: endpoint S3-compatible yang butuh path-style.

Kasus nyata: `R2_ENDPOINT_URL=https://sujinwos.s3.hf.co`, bucket `clipzy`.
Dengan virtual-hosted style boto3 memanggil
`https://clipzy.sujinwos.s3.hf.co/...` (dua level) sementara sertifikat hanya
`*.s3.hf.co` → "SSL validation failed". Path-style memakai
`https://sujinwos.s3.hf.co/clipzy/...` yang cocok.
"""
from __future__ import annotations

from app.services.storage_registry import _needs_path_style


def test_endpoint_hf_co_wajib_path_style():
    assert _needs_path_style({}, "https://sujinwos.s3.hf.co") is True
    assert _needs_path_style({}, "https://s3.hf.co") is True


def test_aws_tetap_virtual_host():
    assert _needs_path_style({}, "https://s3.amazonaws.com") is False
    assert _needs_path_style({}, "https://s3.ap-southeast-1.amazonaws.com") is False


def test_r2_cloudflare_tidak_dipaksa():
    assert _needs_path_style({}, "https://abc123.r2.cloudflarestorage.com") is False


def test_path_style_eksplisit_selalu_menang():
    assert _needs_path_style({"path_style": True}, "https://example.com") is True


def test_endpoint_kosong_aman():
    assert _needs_path_style({}, "") is False
