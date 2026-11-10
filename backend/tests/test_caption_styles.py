"""Unit test preset caption/subtitle (tanpa ffmpeg)."""
import pytest

from app.services.processor import CAPTION_STYLES, get_caption_style

EXPECTED_PRESETS = {
    "classic", "gold", "boxed", "neon", "top", "center",
    # tambahan variasi (Batch UI): karaoke, minimal, impact, boxed gold, pink,
    # headline top, dan caption bar.
    "karaoke", "minimal", "impact", "boxed_gold", "pink", "top_clean", "subtitle_bar",
}


def test_all_presets_exist():
    assert set(CAPTION_STYLES) == EXPECTED_PRESETS


@pytest.mark.parametrize("name", sorted(EXPECTED_PRESETS))
def test_preset_has_valid_force_style_and_overlay(name):
    preset = CAPTION_STYLES[name]
    force_style = preset["force_style"]

    # filtergraph memakai tanda kutip tunggal sebagai pembungkus, jadi nilai
    # tidak boleh mengandung kutip tunggal.
    assert "'" not in force_style
    assert "FontSize=" in force_style
    assert "Outline=" in force_style
    assert "Alignment=" in force_style

    overlay = preset["overlay"]
    assert 0.03 <= overlay["size_ratio"] <= 0.09
    assert overlay["y"] in ("bottom", "top", "center")
    assert 0 <= overlay["border_width"] <= 8
    assert isinstance(overlay["box"], bool)


def test_unknown_style_falls_back_to_classic():
    assert get_caption_style("tidak-ada") is CAPTION_STYLES["classic"]
    assert get_caption_style(None) is CAPTION_STYLES["classic"]
    assert get_caption_style("GOLD") is CAPTION_STYLES["gold"]
