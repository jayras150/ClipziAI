"""Unit test metadata AI klip (validasi grounding) + guard upload YouTube."""
import asyncio

import pytest
from fastapi import HTTPException

from app.services.metadata_generator import (
    MetadataGenerationError,
    MetadataGenerator,
    _clean_tags,
    _extract_json,
    _significant_words,
)
from app.services.youtube_service import YouTubeService

TRANSCRIPT = (
    "Halo guys hari ini aku mau masak mie goreng pedas cepat lima menit. "
    "Bahan dasarnya mie instan, bawang putih, cabai rawit, dan telur. "
    "Tumis bumbu sampai wangi lalu masukkan mie yang sudah direbus."
)


def test_extract_json_membersihkan_code_fence():
    payload = _extract_json('```json\n{"title": "Resep mie"}\n```')
    assert payload == {"title": "Resep mie"}


def test_extract_json_menolak_teks_bukan_json():
    with pytest.raises(MetadataGenerationError):
        _extract_json("tentu, ini judulnya: Resep Mie Goreng")


def test_clean_tags_normalisasi_dan_batasi():
    result = _clean_tags(["#Masak Mie", "masak mie", "MIE-GORENG", "x" * 40])
    assert result == ["masak mie", "mie-goreng"]


def test_significant_words_membuang_stopword():
    words = _significant_words("Ini adalah resep mie yang sangat pedas")
    assert "resep" in words and "mie" in words
    assert "adalah" not in words and "yang" not in words


def test_validate_menolak_kalimat_template():
    generator = MetadataGenerator()
    with pytest.raises(MetadataGenerationError):
        generator._validate(
            {
                "title": "Watch this amazing short clip",
                "description": "Created with Clipzi AI",
                "tags": ["mie goreng", "resep mie", "masak cepat"],
            },
            transcript=TRANSCRIPT,
            variation=0,
        )


def test_validate_menolak_judul_tidak_nyambung_dengan_transkrip():
    generator = MetadataGenerator()
    with pytest.raises(MetadataGenerationError):
        generator._validate(
            {
                "title": "Review kamera mirrorless terbaru 2026",
                "description": "Kamera ini punya sensor besar. #kamera #review #mirrorless",
                "tags": ["kamera", "mirrorless", "review kamera"],
            },
            transcript=TRANSCRIPT,
            variation=0,
        )


def test_validate_menerima_metadata_yang_nyambung():
    generator = MetadataGenerator()
    result = generator._validate(
        {
            "title": "Resep mie goreng pedas 5 menit untuk pemula",
            "description": (
                "Masak mie goreng pedas cuma lima menit dengan bawang putih dan cabai rawit. "
                "Cocok buat sarapan cepat. Simpan resepnya ya. #mie #resep #masak"
            ),
            "tags": ["mie goreng", "resep mie", "masak cepat", "shorts"],
            "hook": "Resep mie goreng pedas 5 menit",
            "language": "id",
        },
        transcript=TRANSCRIPT,
        variation=0,
    )
    assert result["title"].startswith("Resep mie goreng")
    assert len(result["tags"]) >= 3
    assert result["language"] == "id"
    assert result["hook"] == "Resep mie goreng pedas 5 menit"


def test_validate_menolak_tag_semuanya_generik():
    generator = MetadataGenerator()
    with pytest.raises(MetadataGenerationError):
        generator._validate(
            {
                "title": "Resep mie goreng pedas",
                "description": "Mie goreng pedas lima menit. #viral #shorts #trending",
                "tags": ["viral", "shorts", "fyp"],
            },
            transcript=TRANSCRIPT,
            variation=0,
        )


def test_generate_menolak_transkrip_terlalu_pendek(monkeypatch):
    generator = MetadataGenerator()
    # Paksa dianggap "siap" supaya jalur validasi panjang transkrip yang diuji.
    monkeypatch.setattr(generator, "available", True, raising=False)
    with pytest.raises(MetadataGenerationError):
        asyncio.run(generator.generate(transcript="mie goreng enak"))


def test_upload_youtube_butuh_sumber_video():
    service = YouTubeService()
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(service.upload_video(access_token="token", title="Tes"))
    assert excinfo.value.status_code == 400
    assert "Sumber video" in str(excinfo.value.detail)
