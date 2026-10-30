"""Refuse to start a staging/production API that is misconfigured in a way that would be insecure or silently fake.

Local development is exempt (it uses mocks and dev tokens on purpose). Everything here fails fast with ALL the
problems listed, so a deploy is fixed in one go.
"""

from urllib.parse import urlparse

from cryptography.fernet import Fernet

from app.config import Settings

DEFAULT_STORAGE_KEYS = {"minioadmin", ""}


def origin_of(url: str) -> str:
    """scheme://host[:port] of an address, without any path (browsers' Origin and CORS never include one)."""
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}".lower() if u.scheme and u.netloc else url.rstrip("/").lower()


def problems(s: Settings) -> list[str]:
    if s.is_local:
        return []
    out: list[str] = []
    if s.environment not in {"staging", "production"}:
        out.append(f"ENVIRONMENT must be local, staging or production (got {s.environment!r})")
    if s.use_mocks:
        out.append("USE_MOCKS must be false: mocks would fake payments, scans and vendors")
    if s.renderer_backend == "http" and s.use_mocks:
        out.append("RENDERER_BACKEND=http is a local-only override")
    if not s.operator_emails.strip():
        out.append("OPERATOR_EMAILS is required (nobody could sign in to the operator console)")
    if not s.secret_key:
        out.append("SECRET_KEY is required")
    else:
        try:
            Fernet(s.secret_key.encode())
        except Exception:  # noqa: BLE001
            out.append("SECRET_KEY must be a valid Fernet key (urlsafe base64, 32 bytes)")
    if len(s.renderer_shared_secret) < 24:
        out.append("RENDERER_SHARED_SECRET must be set to a long random value (24+ characters)")
    if s.billing_provider == "mock":
        out.append(
            "BILLING_PROVIDER=mock is local-only; use manual (an operator adds credits) or a real payment adapter"
        )
    elif s.billing_provider == "nuvion":
        from app.integrations.billing.nuvion import configuration_problems
        out.extend(configuration_problems(s))
    elif s.billing_provider != "manual" and (not s.billing_webhook_secret or len(s.billing_webhook_secret) < 24):
        out.append("BILLING_WEBHOOK_SECRET must be set to a long random value (24+ characters)")
    if not s.clamd_host and not (s.allow_unscanned_uploads and s.environment == "staging"):
        out.append(
            "CLAMD_HOST is required: uploads are refused without a malware scanner "
            "(staging alone may set ALLOW_UNSCANNED_UPLOADS=true to accept uploads unscanned)"
        )
    if not s.email_api_key:
        out.append("EMAIL_API_KEY is required")
    if s.storage_access_key in DEFAULT_STORAGE_KEYS or s.storage_secret_key in DEFAULT_STORAGE_KEYS:
        out.append("STORAGE_ACCESS_KEY / STORAGE_SECRET_KEY are still the local MinIO defaults")
    if "localhost" in s.database_url or "newsagent:newsagent@" in s.database_url:
        out.append("DATABASE_URL points at a local or default-credential database")
    if "localhost" in s.redis_url:
        out.append("REDIS_URL points at localhost")
    if not s.app_base_url.startswith("https://"):
        out.append("APP_BASE_URL must be https:// (magic links and share links are credentials)")
    if not s.admin_base_url.startswith("https://"):
        out.append("ADMIN_BASE_URL must be https:// (the back office is a sign-in surface)")
    elif s.admin_base_url.rstrip("/") == s.app_base_url.rstrip("/"):
        out.append(
            "ADMIN_BASE_URL must differ from APP_BASE_URL: give the back office its own site, or, when one site serves "
            "both, its own path (ADMIN_BASE_URL=<APP_BASE_URL>/admin)"
        )
    if s.queue_backend != "celery":
        out.append("QUEUE_BACKEND must be celery (the inline queue runs work inside web requests)")
    if not s.trust_proxy_headers:
        out.append("TRUST_PROXY_HEADERS should be true behind Railway, or per-IP rate limits see only the proxy")
    return out


def assert_runtime_ok(s: Settings) -> None:
    found = problems(s)
    if found:
        raise RuntimeError("Refusing to start with an insecure configuration:\n - " + "\n - ".join(found))
