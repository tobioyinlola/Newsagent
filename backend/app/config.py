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
    "llm": VendorPolicy(timeout_s=170, max_attempts=3),
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
    livekit_agent_enabled: bool = (
        False  # set true only once the interviewer agent is deployed; otherwise the browser voice is used
    )
    # Which vendor writes the questions, the story and the content check: "anthropic" or "openai" (any OpenAI-compatible endpoint)
    llm_provider: str = "anthropic"
    llm_api_key: str = ""  # openai only; empty = the same key as TTS_API_KEY / TRANSCRIPTION_API_KEY
    llm_api_url: str = "https://api.openai.com/v1"
    llm_model: str = ""  # empty = the small default of the chosen vendor
    heygen_api_key: str = ""
    # Which AI B-roll provider to use. No real provider is implemented yet, so outside mock mode this stays empty and
    # AI B-roll reports itself unavailable instead of pretending.
    broll_provider: str = ""
    # Optional. When set, POST /v1/webhooks/heygen is live: the signature is an HMAC-SHA256 of the raw body, read from the
    # header below. The event only wakes the pipeline up (it never supplies results), so a forged event cannot inject media.
    # The look used when a project doesn't choose a presenter. Required for real runs: HeyGen needs an avatar id.
    heygen_default_avatar_id: str = ""
    heygen_voice_male: str = ""  # voice used when a presenter's look has no voice of its own and the presenter is a man
    heygen_voice_female: str = ""  # ... and a woman
    heygen_closing_params: str = (
        ""  # JSON object merged into the HeyGen request for the closing sign-off clip only (expression/smile settings)
    )
    heygen_default_voice_id: str = ""  # optional: used for any presenter whose look has no voice of its own
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
    # Extra browser origins allowed to call the API, as one regular expression (e.g. this project's Vercel preview sites, which get a
    # new address per branch). Empty: only APP_BASE_URL and ADMIN_BASE_URL.
    cors_origin_regex: str = ""
    email_reply_to: str = ""  # optional: a monitored mailbox; replies from people (and a real, answered address) help mail land in the inbox
    email_from: str = "Newsroom <no-reply@localhost>"
    storage_endpoint: str = "http://localhost:9000"
    storage_bucket: str = "newsagent"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    renderer_url: str = "http://localhost:4000"
    renderer_shared_secret: str = ""
    open_signup_enabled: bool = True  # anyone can create a workspace by confirming their email (no invitation needed)
    signup_credits: str = "5"  # credits a new workspace starts with when it signs up on its own
    invite_ttl_hours: int = 336  # how long an emailed invitation to join stays valid (never less than 48 hours)
    otp_ttl_minutes: int = 10
    session_idle_minutes: int = 60
    session_absolute_days: int = 30
    operator_session_hours: int = 8
    sentry_dsn: str = ""
    app_base_url: str = "http://localhost:5173"
    admin_base_url: str = "http://localhost:5173/admin"  # the back office: the customer app's site under /admin (or, if you host it apart, its own https address)
    environment: str = "local"  # local, staging, production
    # ENFORCE_LIMITS=false: video creation is never refused for credits, spend caps, vendor budgets, a maintenance pause or request
    # rate limits. Spend is still recorded. Sign-in throttles, webhook/share limits and the suspended flag always apply.
    enforce_limits: bool = True
    # true: every finished video is also rendered in vertical 9:16. Off by default: it doubles the final render time.
    render_vertical: bool = False
    # true: every video opens with the Cover Founder intro (5 s) and closes with the outro (6 s).
    brand_cards: bool = True
    live_location: str = "Toronto, Canada"  # the LIVE badge on every video (blank hides it)
    live_timezone: str = "America/Toronto"  # the published date and time stamp is shown in this zone
    # false: content that only needs a second look (not clearly disallowed) goes ahead without waiting for an operator. Clearly
    # disallowed content is still blocked.
    moderation_hold_for_review: bool = True
    use_mocks: bool = True
    # Mock vendors normally answer at once. Above 0 they behave like real ones: a presenter clip and a render each take this many
    # seconds (the avatar mock then submits and is polled, so vendor slots, waiting and queueing are exercised). For load tests.
    mock_vendor_latency_s: float = 0.0
    operator_emails: str = ""  # comma separated; may call /admin
    queue_backend: str = "inline"  # inline | celery
    # Database connections per process (the API, and each worker). Keep (pool_size + max_overflow) x processes under Postgres's
    # max_connections. A request waits up to db_pool_timeout_s for a free connection, then fails fast instead of piling up.
    # With the Celery queue, a worker waits at most this long on a presenter clip, then is released and the same vendor job is polled
    # again shortly. Workers are the scarce thing: without this, each clip in progress would hold one for its whole (minutes-long) wait.
    vendor_hold_s: float = 45.0
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout_s: int = 20
    db_pool_recycle_s: int = (
        1800  # replace connections older than this, so a database/proxy idle-timeout never hands out a dead one
    )
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
    # Staging only, and a deliberate trade: with no ClamAV, uploads (founder videos, pictures) are accepted without a virus scan.
    allow_unscanned_uploads: bool = False
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
