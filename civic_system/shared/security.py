# shared/security.py
"""
Security utilities: cryptographic OTP generation, email hashing,
Fernet encryption/decryption, OTP hashing, and CSRF tokens.
"""

import hashlib
import hmac
import os
import secrets
import string

from cryptography.fernet import Fernet
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import bcrypt

# ---------------------------------------------------------------------------
# Environment-loaded secrets (loaded once at import time via dotenv)
# ---------------------------------------------------------------------------

_ENCRYPTION_KEY: bytes | None = None
_CSRF_SERIALIZER: URLSafeTimedSerializer | None = None
_COOKIE_SERIALIZER: URLSafeTimedSerializer | None = None


def _get_encryption_key() -> bytes:
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is None:
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("ENCRYPTION_KEY is not set in environment.")
        _ENCRYPTION_KEY = key.encode()
    return _ENCRYPTION_KEY


def _get_csrf_serializer() -> URLSafeTimedSerializer:
    global _CSRF_SERIALIZER
    if _CSRF_SERIALIZER is None:
        secret = os.getenv("CSRF_SECRET")
        if not secret:
            raise RuntimeError("CSRF_SECRET is not set in environment.")
        _CSRF_SERIALIZER = URLSafeTimedSerializer(secret, salt="csrf-token")
    return _CSRF_SERIALIZER


def _get_cookie_serializer() -> URLSafeTimedSerializer:
    global _COOKIE_SERIALIZER
    if _COOKIE_SERIALIZER is None:
        secret = os.getenv("COOKIE_SECRET")
        if not secret:
            raise RuntimeError("COOKIE_SECRET is not set in environment.")
        _COOKIE_SERIALIZER = URLSafeTimedSerializer(secret, salt="session-cookie")
    return _COOKIE_SERIALIZER


# ---------------------------------------------------------------------------
# OTP Generation — cryptographically secure
# ---------------------------------------------------------------------------

def generate_otp() -> str:
    """
    Generates a 6-digit numeric OTP as string using CSPRNG.
    """
    return "".join(secrets.choice(string.digits) for _ in range(6))


# ---------------------------------------------------------------------------
# Email hashing (SHA-256, deterministic, one-way)
# ---------------------------------------------------------------------------

def hash_email(email: str) -> str:
    """
    Returns a deterministic SHA-256 hex digest of the lowercase email.
    Used for lookups where the original email is not needed.
    """
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Email encryption (Fernet, reversible)
# ---------------------------------------------------------------------------

def encrypt_email(email: str) -> str:
    """
    Encrypts an email with Fernet symmetric encryption.
    Returns a URL-safe base64-encoded string.
    Used when the original email must be recoverable (e.g., sending notifications).
    """
    fernet = Fernet(_get_encryption_key())
    return fernet.encrypt(email.strip().lower().encode("utf-8")).decode("utf-8")


def decrypt_email(token: str) -> str:
    """
    Decrypts a Fernet-encrypted email token back to the original email.
    """
    fernet = Fernet(_get_encryption_key())
    return fernet.decrypt(token.encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# OTP hashing (HMAC-SHA256 — fast, deterministic, sufficient for short-lived OTPs)
# ---------------------------------------------------------------------------

def hash_otp(otp: str) -> str:
    """
    Hash an OTP using HMAC-SHA256 with the encryption key as the HMAC key.
    OTPs are short-lived (5 min), so HMAC is appropriate and fast.
    """
    key = _get_encryption_key()
    return hmac.new(key, otp.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """
    Verify an OTP against its HMAC-SHA256 hash (constant-time comparison).
    """
    computed = hash_otp(plain_otp)
    return hmac.compare_digest(computed, hashed_otp)


# ---------------------------------------------------------------------------
# CSRF Tokens
# ---------------------------------------------------------------------------

def generate_csrf_token(session_id: str = "global") -> str:
    """
    Generate a time-limited CSRF token signed with the CSRF secret.
    """
    return _get_csrf_serializer().dumps(session_id)


def validate_csrf_token(token: str, max_age_seconds: int = 3600) -> bool:
    """
    Validate a CSRF token. Returns True if valid and not expired.
    """
    try:
        _get_csrf_serializer().loads(token, max_age=max_age_seconds)
        return True
    except (BadSignature, SignatureExpired):
        return False


# ---------------------------------------------------------------------------
# Signed Session Cookies
# ---------------------------------------------------------------------------

def sign_session(email: str) -> str:
    """
    Create a signed session value from an email.
    The raw email is NOT stored in the cookie — only a signed token.
    """
    return _get_cookie_serializer().dumps(email.strip().lower())


def unsign_session(token: str, max_age_seconds: int = 28800) -> str | None:
    """
    Recover the email from a signed session cookie.
    Returns None if invalid or expired (default 8-hour expiry).
    """
    try:
        return _get_cookie_serializer().loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


# ---------------------------------------------------------------------------
# Input Sanitization
# ---------------------------------------------------------------------------

def sanitize_input(value: str, max_length: int = 5000) -> str:
    """
    Basic input sanitization: strip leading/trailing whitespace,
    truncate to max_length, and remove null bytes.
    """
    if not value:
        return value
    return value.strip().replace("\x00", "")[:max_length]


# ---------------------------------------------------------------------------
# Password Hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
