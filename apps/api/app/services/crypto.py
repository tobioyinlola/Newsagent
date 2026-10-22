"""Symmetric encryption for the few secrets we must be able to read back (e.g. reminder links)."""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    s = get_settings()
    if s.secret_key:
        return Fernet(s.secret_key.encode())
    if not s.is_local:
        raise RuntimeError("SECRET_KEY must be set outside local development")
    # Deterministic dev-only key so local data survives restarts. Never used outside ENVIRONMENT=local.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"newsagent-local-dev-key").digest()))


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
