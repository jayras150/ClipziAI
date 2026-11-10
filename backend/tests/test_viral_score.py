"""Unit test skor viral (tanpa DB/ffmpeg)."""
from app.services.viral import POWER_WORDS, score_clip


def test_strong_transcript_scores_higher_than_empty():
    strong = score_clip(
        transcript=(
            "Jangan pernah lakukan 3 kesalahan ini saat edit video! "
            "Pertama, kamu harus potong jeda yang bikin orang bosan. "
            "Kedua, subtitle wajib karena 80 persen orang nonton tanpa suara. "
            "Ketiga, hook 3 detik pertama menentukan clip kamu viral atau tidak. "
            "Simpan video ini biar kamu tidak rugi waktu edit!"
        ),
        duration=28,
        has_subtitle=True,
        has_caption=False,
    )
    weak = score_clip(transcript="", duration=28, has_subtitle=True)
    assert strong["score"] > weak["score"]
    assert weak["factors"].get("estimated") is not True


def test_score_always_in_range_and_has_factors():
    for transcript in ("", "halo", "Ini rahasia cara cepat viral! " * 20):
        for duration in (0, 5, 28, 120):
            result = score_clip(transcript=transcript, duration=duration)
            assert 28.0 <= result["score"] <= 97.0
            for key in ("hook", "duration", "pacing", "emotion", "clarity"):
                assert 0.0 <= result["factors"][key] <= 1.0
            assert isinstance(result["factors"]["label"], str)


def test_estimated_flag_and_reasoning_present():
    result = score_clip(transcript="", duration=95, estimated=True)
    assert result["factors"]["estimated"] is True
    assert result["factors"]["reasoning"]


def test_duration_outside_sweet_spot_lowers_fit():
    good = score_clip(transcript="cara cepat viral", duration=30)
    too_long = score_clip(transcript="cara cepat viral", duration=300)
    assert good["factors"]["duration"] > too_long["factors"]["duration"]


def test_power_words_are_lowercase_strings():
    assert POWER_WORDS
    assert all(word == word.lower() for word in POWER_WORDS)
