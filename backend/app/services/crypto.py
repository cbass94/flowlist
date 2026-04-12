"""
Token encryption at rest.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
The Fernet key is derived from SECRET_KEY via SHA-256 so it is always
exactly 32 bytes, regardless of the secret's length.

All OAuth access/refresh tokens are encrypted before writing to the DB and
decrypted on the way out. The cipher is transparent to the rest of the app.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    raw = hashlib.sha256(settings.secret_key.encode()).digest()  # 32 bytes
    key = base64.urlsafe_b64encode(raw)  # Fernet requires urlsafe-base64 32-byte key
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the Fernet token as a string."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """
    Decrypt a Fernet token. Raises ValueError for invalid/tampered ciphertext.
    Callers should treat this as a hard auth failure (force re-login).
    """
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception) as exc:
        raise ValueError("Token decryption failed — token may be corrupted") from exc
