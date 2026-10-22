"""RFC 6238 time-based one-time passwords (Google Authenticator, 1Password, Authy...). Standard library only."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_S = 30
DIGITS = 6
WINDOW = 1  # accept the previous and next 30 s step too (clock drift)


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")  # 160 bits


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    n = (struct.unpack(">I", digest[off : off + 4])[0] & 0x7FFFFFFF) % (10**DIGITS)
    return str(n).zfill(DIGITS)


def verify(secret: str, code: str, last_step: int | None = None, now: float | None = None) -> int | None:
    """Return the matching time step, or None. A step at or before `last_step` is refused (a code can't be replayed)."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    current = int((now if now is not None else time.time()) // STEP_S)
    for step in range(current - WINDOW, current + WINDOW + 1):
        if hmac.compare_digest(_code(secret, step), code):
            return step if (last_step is None or step > last_step) else None
    return None


def provisioning_uri(secret: str, email: str, issuer: str = "Newsagent") -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP_S}"
