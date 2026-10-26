"""Environment-driven settings plus per-vendor timeout/retry/concurrency policy."""

from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class VendorPolicy(BaseModel):
    timeout_s: float = 60
    max_attempts: int = 4
    backoff_base_s: float = 2
    max_concurrency: int = 4


# One place for timeouts, retries and concurrency per vendor (spec section 3).
VENDOR_POLICIES: dict[str, VendorPolicy] = {
    "llm": VendorPolicy(timeout_s=90, max_attempts=3),
    "avatar": VendorPolicy(timeout_s=900, max_attempts=3, max_concurrency=3),
    "renderer": VendorPolicy(timeout_s=1200, max_attempts=2, max_concurrency=2),
    "transcription": VendorPolicy(timeout_s=300, max_attempts=3),
    "email": VendorPolicy(timeout_s=20, max_attempts=5),
    "tts": VendorPolicy(timeout_s=30, max_attempts=2),  # the interviewer's voice
    "broll": VendorPolicy(timeout_s=300, max_attempts=2),  # optional AI-generated product shots
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://newsagent:newsagent@localhost:5432/newsagent"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""
    # LiveKit (optional): the interview room. All three set = the browser joins a LiveKit room and the interviewer agent speaks.
    livekit_url: str = ""  # wss://<project>.livekit.cloud
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "cf-interviewer"
    llm_model: str = ""  # empty = the small default in integrations/llm/anthropic.py
    heygen_api_key: str = ""
    # Which AI B-roll provider to use. No real provider is implemented yet, so outside mock mode this stays empty and
    # AI B-roll reports itself unavailable instead of pretending.
    broll_provider: str = ""
    # Optional. When set, POST /v1/webhooks/heygen is live: the signature is an HMAC-SHA256 of the raw body, read from the
    # header below. The event only wakes the pipeline up (it never supplies results), so a forged event cannot inject media.
    # The look used when a project doesn't choose a presenter. Required for real runs: HeyGen needs an avatar id.
    heygen_default_avatar_id: str = ""
    # Looks whose video already contains the whole studio (a photo of a news set that the vendor animates). Those are
    # requested as ordinary MP4 and shown full frame; every other look is requested as a transparent cut-out.
    heygen_fullframe_avatar_ids: str = ""
    # presenters offered first and always valid: "id|Name|gender;id|Name|gender". Their pictures are the frontend's /presenters/<id>.jpg
    heygen_featured_presenters: str = ""
    heygen_webhook_secret: str = ""
    heygen_webhook_signature_header: str = "signature"
    synthesia_api_key: str = ""
    transcription_api_key: str = ""
    email_api_key: str = ""
    email_from: str = "Newsroom <no-reply@localhost>"
    storage_endpoint: str = "http://localhost:9000"
    storage_bucket: str = "newsagent"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    renderer_url: str = "http://localhost:4000"
    renderer_shared_secret: str = ""
    otp_ttl_minutes: int = 10
    session_idle_minutes: int = 60
    session_absolute_days: int = 30
    operator_session_hours: int = 8
    sentry_dsn: str = ""
    app_base_url: str = "http://localhost:5173"
    admin_base_url: str = "http://localhost:5174"  # the back-office app, a separate site from the customer app
    environment: str = "local"  # local, staging, production
    use_mocks: bool = True
    operator_emails: str = ""  # comma separated; may call /admin
    queue_backend: str = "inline"  # inline | celery
    rate_limit_backend: str = ""  # "memory" | "redis"; default: redis outside local
    trust_proxy_headers: bool = False  # True behind Railway/Cloudflare so X-Forwarded-For identifies clients
    secret_key: str = ""  # Fernet key (urlsafe base64, 32 bytes) for encrypting reminder links; required outside local
    interview_expiry_days: int = 14
    interview_reminder_days: str = "2,5,9"  # days after the invite when reminders are sent
    raw_take_retention_days: int = 90
    transcription_api_url: str = "https://api.openai.com/v1"  # any OpenAI-compatible /audio/transcriptions endpoint
    transcription_model: str = "whisper-1"
    tts_api_key: str = ""  # an OpenAI key; falls back to TRANSCRIPTION_API_KEY (same account)
    tts_api_url: str = "https://api.openai.com/v1"  # any OpenAI-compatible /audio/speech endpoint
    tts_model: str = "tts-1"
    tts_voice: str = "nova"
    renderer_backend: str = (
        ""  # "http" uses the real renderer service even when USE_MOCKS=true (local full-stack tests)
    )
    local_storage_dir: str = ""  # shared folder for LocalStorage so a local renderer can read/write the same files
    mock_anchor_file: str = ""  # a real .webm the mock avatar copies as its output, for local end-to-end renders
    usd_per_credit: str = "1"  # what one credit is worth in revenue, for margin reporting
    credit_markup: str = (
        "1"  # customer credits charged per 1 USD of vendor cost (pass-through until pricing is decided)
    )
    low_balance_threshold: str = "5"
    billing_webhook_secret: str = ""  # HMAC secret for payment webhooks; REQUIRED outside local
    billing_provider: str = "mock"  # mock (local only) | manual (an operator adds credits; no checkout) | a real adapter, still to be chosen (Stripe / Paystack / Flutterwave)
    clamd_host: str = ""  # ClamAV daemon; required for uploads when USE_MOCKS=false
    clamd_port: int = 3310
    api_public_url: str = "http://localhost:8000"  # used by local dev storage URLs

    @property
    def rate_limit_store(self) -> str:
        return self.rate_limit_backend or ("memory" if self.is_local else "redis")

    @property
    def is_local(self) -> bool:
        return self.environment == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
