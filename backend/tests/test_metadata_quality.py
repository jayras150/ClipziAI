"""
Validasi metadata AI: judul tidak boleh menyalin transkrip mentah.

Regresi: hasil AI dulu sering berupa potongan transkrip apa adanya ("jadi gini
guys saya mau kasih tips..."), bukan hook. Sekarang judul yang menyalin 7+ kata
berurutan dari transkrip ditolak, begitu juga judul yang terlalu pendek.
"""
from __future__ import annotations

import pytest

from app.services.metadata_generator import (
    MetadataGenerationError,
    MetadataGenerator,
    MIN_COPIED_WORDS,
    build_heuristic_metadata,
)

TRANSCRIPT = (
    "jadi gini guys saya mau kasih tips budgeting yang benar buat anak muda "
    "supaya gaji tidak habis sebelum akhir bulan dan bisa mulai nabung"
)


def _generator() -> MetadataGenerator:
    # client dummy: `_validate` tidak memakai client
    return MetadataGenerator(client=object(), model="dummy")


def test_judul_menyalin_transkrip_ditolak():
    payload = {
        "title": "saya mau kasih tips budgeting yang benar buat anak muda",
        "description": "Budgeting tetap sulit karena satu kebiasaan kecil. "
        "#budgeting #keuangan #anakmuda",
        "tags": ["budgeting", "keuangan", "nabung", "gaji", "anak muda", "tips"],
        "hook": "Gaji habis sebelum akhir bulan?",
        "language": "id",
    }
    with pytest.raises(MetadataGenerationError) as excinfo:
        _generator()._validate(payload, transcript=TRANSCRIPT, variation=0)
    assert "copied verbatim" in str(excinfo.value)


def test_judul_hasil_rewrite_diterima():
    payload = {
        "title": "Budgeting Rule That Saved 40% of My Salary",
        "description": "Sisihkan tabungan di awal, bukan di akhir. "
        "Pola 50/30/20 gagal karena urutan transfernya salah. #budgeting #nabung",
        "tags": ["budgeting", "nabung", "gaji", "keuangan", "tips", "anak muda"],
        "hook": "Gaji habis sebelum akhir bulan?",
        "viral_reason": "Angka 40% membuat klaim konkret dan mudah dipercaya.",
        "language": "id",
    }
    result = _generator()._validate(payload, transcript=TRANSCRIPT, variation=0)
    assert result["title"] == payload["title"]
    assert result["viral_reason"].startswith("Angka 40%")
    assert len(result["tags"]) >= 3


def test_judul_terlalu_pendek_ditolak():
    payload = {
        "title": "Tips gaji",
        "description": "Penjelasan singkat tentang budgeting dan menabung. #budgeting",
        "tags": ["budgeting", "nabung", "gaji", "keuangan"],
        "hook": "Gaji habis?",
        "language": "id",
    }
    with pytest.raises(MetadataGenerationError) as excinfo:
        _generator()._validate(payload, transcript=TRANSCRIPT, variation=0)
    assert "too short" in str(excinfo.value)


def test_batas_kata_salinan_konsisten():
    assert MIN_COPIED_WORDS >= 5


def test_heuristic_memakai_bahasa_inggris():
    meta = build_heuristic_metadata("Budgeting keeps failing because of one line item.", duration=42)
    assert "Key topics" not in meta["description"] or "Topik" not in meta["description"]
    assert meta["viral_reason"] is None
