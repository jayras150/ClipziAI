"""
Security core: Argon2id password hashing, AES-256-GCM field encryption,
JWT token management, CSRF protection, rate limiting helpers.
"""
import os
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple
from uuid import uuid4

import pyotp
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Password Hashing (Argon2id)
# ---------------------------------------------------------------------------
ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against Argon2id hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# AES-256-GCM Field Encryption
# ---------------------------------------------------------------------------
def _get_aesgcm() -> AESGCM:
    """Return AESGCM instance using ENCRYPTION_KEY from env."""
    key_b64 = settings.ENCRYPTION_KEY
    try:
        key = base64.b64decode(key_b64)
    except Exception:
        # Fallback: derive key from SECRET_KEY (not recommended for production)
        key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    if len(key) != 32:
        key = hashlib.sha256(key).digest()
    return AESGCM(key)


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string field using AES-256-GCM. Returns base64-encoded ciphertext."""
    aesgcm = _get_aesgcm()
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_field(ciphertext_b64: str) -> str:
    """Decrypt a base64-encoded AES-256-GCM ciphertext."""
    aesgcm = _get_aesgcm()
    data = base64.b64decode(ciphertext_b64)
    nonce, ct = data[:12], data[12:]
    plaintext = aesgcm.decrypt(nonce, ct, None)
    return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# JWT Token Management
# ---------------------------------------------------------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token (default dari setting ACCESS_TOKEN_MINUTES)."""
    to_encode = data.copy()
    lifetime = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    expire = datetime.now(timezone.utc) + lifetime
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT refresh token (default dari setting REFRESH_TOKEN_DAYS)."""
    to_encode = data.copy()
    lifetime = expires_delta or timedelta(days=settings.REFRESH_TOKEN_DAYS)
    expire = datetime.now(timezone.utc) + lifetime
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify JWT token."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Two-Factor Authentication (TOTP)
# ---------------------------------------------------------------------------
def generate_totp_secret() -> str:
    """Generate a new TOTP secret key."""
    return pyotp.random_base32()


def get_totp_uri(email: str, secret: str) -> str:
    """Generate TOTP provisioning URI for authenticator apps."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Clipzi AI")


def verify_totp(secret: str, otp: str) -> bool:
    """Verify a TOTP OTP code."""
    return pyotp.TOTP(secret).verify(otp)


def generate_backup_codes(count: int = 8) -> list[str]:
    """Generate backup codes for 2FA recovery."""
    return [secrets.token_hex(4) for _ in range(count)]


# ---------------------------------------------------------------------------
# API Key Utilities
# ---------------------------------------------------------------------------
def generate_api_key() -> Tuple[str, str]:
    """Generate a new API key. Returns (raw_key, key_hash)."""
    raw = f"{settings.API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, key_hash


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    """Verify raw API key against stored hash."""
    computed = hashlib.sha256(raw_key.encode()).hexdigest()
    return computed == key_hash


# ---------------------------------------------------------------------------
# CSRF Token
# ---------------------------------------------------------------------------
def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)