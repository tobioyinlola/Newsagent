"""Password hashing (scrypt from the standard library) and the password policy."""

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**15, 8, 1  # ~32 MiB, tens of milliseconds
_MAXMEM = 64 * 1024 * 1024
COMMON = {
    "password12",
    "1234567890",
    "qwertyuiop",
    "password123",
    "0123456789",
    "iloveyou12",
    "letmein123",
    "welcome123",
}


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=_MAXMEM)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = _derive(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time. A missing hash still costs one derivation, so timing doesn't reveal which emails have a password."""
    if not stored:
        _derive(password, b"\0" * 16, N, R, P)
        return False
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def policy_error(password: str, email: str) -> str | None:
    if len(password) < 10:
        return "Use at least 10 characters."
    if len(password) > 128:
        return "Use at most 128 characters."
    low = password.lower()
    if low in COMMON or low == email.lower() or email.split("@")[0].lower() in low and len(email.split("@")[0]) >= 4:
        return "That password is too easy to guess. Avoid your email address and common passwords."
    if len(set(password)) < 5:
        return "That password is too easy to guess. Mix in more different characters."
    return None
