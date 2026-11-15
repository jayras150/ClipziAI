"""Unit test device reputation (tanpa DB/network)."""
from app.services.device_reputation import (
    DEFAULT_DEVICE_SETTING,
    calculate_risk_score,
    hash_fingerprint,
    normalize_device_setting,
    normalize_fingerprint,
    risk_status,
)


def test_new_device_is_low_risk():
    score = calculate_risk_score(
        account_count=1,
        claim_count=0,
        email_verified=False,
        has_fingerprint=True,
    )
    assert score == 0
    assert risk_status(score) == "NEW"


def test_duplicate_account_and_claim_is_high_risk():
    score = calculate_risk_score(
        account_count=3,
        claim_count=1,
        email_verified=False,
        has_fingerprint=True,
    )
    assert score == 100
    assert risk_status(score) == "HIGH_RISK"


def test_verified_email_reduces_score_and_clamped():
    score = calculate_risk_score(
        account_count=1,
        claim_count=0,
        email_verified=True,
        has_fingerprint=True,
    )
    assert score == 0
    assert 0 <= score <= 100


def test_missing_fingerprint_adds_risk():
    score = calculate_risk_score(
        account_count=1,
        claim_count=0,
        email_verified=False,
        has_fingerprint=False,
    )
    assert score == 20
    assert risk_status(score) == "NEW"


def test_fingerprint_is_hashed_not_raw():
    raw = "device-abc-123"
    digest = hash_fingerprint(raw)
    assert digest != raw
    assert len(digest) == 64
    assert digest == hash_fingerprint(raw)


def test_normalize_fingerprint_truncates():
    assert normalize_fingerprint("  abc  ") == "abc"
    assert len(normalize_fingerprint("x" * 1000)) == 512


def test_device_setting_defaults_and_clamp():
    assert normalize_device_setting({}) == DEFAULT_DEVICE_SETTING
    assert normalize_device_setting({"enforce_device_claim": True, "signup_bonus": 999})[
        "signup_bonus"
    ] == 100
    assert normalize_device_setting({"signup_bonus": -5})["signup_bonus"] == 0
