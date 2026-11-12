"""Regression test metadata heuristik (dipakai saat LLM gagal/timeout)."""
from app.services.metadata_generator import build_heuristic_metadata

TRANSCRIPT = (
    "Jadi, saya belajar coding dari nol sampai bisa bikin aplikasi sendiri. "
    "Ini butuh disiplin tinggi setiap hari. "
    "Coding itu menyenangkan kalau konsisten!"
)


def test_judul_dari_kalimat_pertama_tanpa_filler():
    meta = build_heuristic_metadata(
        TRANSCRIPT, duration=63.9, start_time="00:01:42", end_time="00:02:46"
    )
    assert meta["title"].startswith("Saya belajar coding")
    assert not meta["title"].lower().startswith("jadi")
    assert meta["title"].endswith(".") is False
    assert "00:01:42" not in meta["title"]


def test_deskripsi_memuat_kalimat_awal_akhir_dan_topik():
    meta = build_heuristic_metadata(TRANSCRIPT, duration=63.9)
    assert "belajar coding" in meta["description"]
    assert "konsisten" in meta["description"].lower()
    assert "Topik utama:" in meta["description"]


def test_tag_dari_kata_kunci_transkrip_dan_tidak_kosong():
    meta = build_heuristic_metadata(TRANSCRIPT, duration=63.9)
    assert "coding" in meta["tags"]
    assert "shorts" in meta["tags"]
    assert len(meta["tags"]) <= 12
    assert meta["heuristic"] is True


def test_transkrip_kosong_tetap_menghasilkan_judul():
    meta = build_heuristic_metadata("", duration=61.0, start_time="00:00:10")
    assert meta["title"].strip()
    assert meta["description"].strip()
    assert meta["hook"].strip()


def test_timestamp_disimpan_terpisah_bukan_di_judul():
    meta = build_heuristic_metadata(
        TRANSCRIPT, duration=61.0, start_time="00:02:00", end_time="00:03:01"
    )
    assert meta["start_time"] == "00:02:00"
    assert meta["end_time"] == "00:03:01"
    assert meta["duration"] == 61.0
    assert "00:02:00" not in meta["title"]
