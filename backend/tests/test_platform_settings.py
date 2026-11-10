"""Unit test konfigurasi watermark platform + mapping posisi (tanpa DB)."""
from app.services.platform_settings import (
    DEFAULT_WATERMARK,
    normalize_watermark,
    plan_is_watermarked,
)
from app.services.platform_watermark import _position_xy


def test_defaults_when_value_missing():
    config = normalize_watermark(None)
    assert config["enabled"] is False
    assert config["plans"] == ["free"]
    assert config["position"] == "bottom-right"
    assert config["text"] == DEFAULT_WATERMARK["text"]


def test_values_are_clamped_and_sanitized():
    config = normalize_watermark(
        {
            "opacity": 5,
            "scale": 0.0001,
            "margin": 9999,
            "position": "tengah",
            "text_color": "red",
            "plans": ["free", "enterprise", "PRO"],
            "text": "x" * 100,
        }
    )
    assert config["opacity"] == 1.0
    assert config["scale"] == 0.05
    assert config["margin"] == 200
    assert config["position"] == "bottom-right"
    assert config["text_color"] == "#ffffff"
    assert config["plans"] == ["free", "pro"]
    assert len(config["text"]) == 60


def test_empty_plans_falls_back_to_free():
    assert normalize_watermark({"plans": []})["plans"] == ["free"]
    assert normalize_watermark({"plans": "free"})["plans"] == ["free"]


def test_plan_is_watermarked_matrix():
    config = normalize_watermark({"enabled": True, "plans": ["free"]})
    assert plan_is_watermarked("free", config) is True
    assert plan_is_watermarked(None, config) is True  # None dianggap free
    assert plan_is_watermarked("pro", config) is False

    disabled = normalize_watermark({"enabled": False, "plans": ["free", "pro"]})
    assert plan_is_watermarked("free", disabled) is False
    assert plan_is_watermarked("pro", disabled) is False


def test_position_expressions_include_margin():
    assert _position_xy("bottom-right", 48) == ("w-text_w-48", "h-text_h-48")
    assert _position_xy("top-left", 10) == ("10", "10")
    assert _position_xy("center", 99) == ("(w-text_w)/2", "(h-text_h)/2")
    # posisi tak dikenal jatuh ke kanan bawah
    assert _position_xy("ngawur", 24) == ("w-text_w-24", "h-text_h-24")
