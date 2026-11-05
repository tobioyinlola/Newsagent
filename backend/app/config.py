"""Environment-driven settings plus per-vendor timeout/retry/concurrency policy."""

import os
from collections.abc import Mapping
from decimal import Decimal
from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VendorPolicy(BaseModel):
    timeout_s: float = 60
    max_attempts: int = 4
    backoff_base_s: float = 2
    max_concurrency: int = 4


def _env_int(environ: Mapping[str, str], name: str, default: int, minimum: int = 1) -> int:
    """A whole number from the environment, or the default when it is unset, empty or not a number."""
    try:
        return max(minimum, int(environ.get(name, "").strip() or default))
    except ValueError:
        return default


def build_vendor_policies(environ: Mapping[str, str]) -> dict[str, VendorPolicy]:
    """One place for timeouts, retries and concurrency per vendor (spec section 3). How many presenter-video jobs may run at once is
    what the HeyGen plan allows, so it is a setting (AVATAR_MAX_CONCURRENCY, 3 unless set); the same for the renderer."""
    return {
        "llm": VendorPolicy(timeout_s=170, max_attempts=3),
        "avatar": VendorPolicy(timeout_s=900, max_attempts=3, max_concurrency=_env_int(environ, "AVATAR_MAX_CONCURRENCY", 3)),
        # A render of a 5 to 6 minute interview video takes about 20 minutes on the production server (about 9 frames a second), so one
        # attempt gets an hour. The worker lease (runner.lease_for, used by the stuck-project sweep) is worked out from this number too.
        "renderer": VendorPolicy(
            timeout_s=3600, max_attempts=2, max_concurrency=_env_int(environ, "RENDERER_MAX_CONCURRENCY", 2)
        ),
        "transcription": VendorPolicy(timeout_s=300, max_attempts=3),
        "email": VendorPolicy(timeout_s=20, max_attempts=5),
        "tts": VendorPolicy(timeout_s=30, max_attempts=2),  # the interviewer's voice
        "broll": VendorPolicy(timeout_s=300, max_attempts=2),  # optional AI-generated product shots
    }


VENDOR_POLICIES: dict[str, VendorPolicy] = build_vendor_policies(os.environ)


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
    # Editorial Breaking Story presenter only. The customer video pipeline keeps using heygen_default_avatar_id.
    # This is the female news-desk look already listed as coming soon in the presenter catalogue.
    news_desk_avatar_id: str = "294e7a4a0fc0e8bc6d4990e34f5365fc"  # "Studio anchor": at a news desk, face clear of the headline
    news_desk_voice_gender: str = "female"  # the News Desk presenter always speaks with a voice of this gender ("" = the look's own)
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
    heygen_extra_presenters: str = ""  # more house presenters, same format as above; added after them (so a new one never has to rewrite the list above)
    heygen_webhook_secret: str = ""
    heygen_webhook_signature_header: str = "signature"
    synthesia_api_key: str = ""
    transcription_api_key: str = ""
    email_api_key: str = ""
    # Extra browser origins allowed to call the API, as one regular expression (e.g. this project's Vercel preview sites, which get a
    # new address per branch). Empty: only APP_BASE_URL and ADMIN_BASE_URL.
    cors_origin_regex: str = ""
    email_reply_to: str = ""  # optional: a monitored mailbox; replies from people (and a real, answered address) help mail land in the inbox
    email_max_per_second: float = 5.0  # sends are spaced to at most this many a second, so a burst of sign-ups stays under the provider's limit (0 = off)
    email_from: str = "Newsroom <no-reply@localhost>"
    storage_endpoint: str = "http://localhost:9000"
    storage_bucket: str = "newsagent"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    renderer_url: str = "http://localhost:4000"
    renderer_urls: str = ""  # several renderers: comma separated `url` or `name=url` (e.g. main=http://127.0.0.1:4000,r2=http://renderer-2.railway.internal:4000). Unset = just renderer_url.
    renderer_shared_secret: str = ""
    open_signup_enabled: bool = True  # anyone can create a workspace by confirming their email (no invitation needed)
    signup_credits: str = "1"  # credits a new workspace starts with when it signs up on its own: one free video
    signup_per_ip_per_hour: int = (
        20  # sign-up codes one address may ask for in an hour (the automated browser tests raise it)
    )
    invite_ttl_hours: int = 336  # how long an emailed invitation to join stays valid (never less than 48 hours)
    otp_ttl_minutes: int = 10
    session_idle_minutes: int = 60
    session_absolute_days: int = 30
    operator_session_hours: int = 8
    sentry_dsn: str = ""
    app_base_url: str = "http://localhost:5173"
    admin_base_url: str = "http://localhost:5173/admin"  # the back office: the customer app's site under /admin (or, if you host it apart, its own https address)
    environment: str = "local"  # local, staging, production
    # ENFORCE_LIMITS=false: video creation is never refused for spend caps (a video ALWAYS needs its credit), vendor budgets, a maintenance pause or request
    # rate limits. Spend is still recorded. Sign-in throttles, webhook/share limits and the suspended flag always apply.
    enforce_limits: bool = True
    # true: every finished video is also rendered in vertical 9:16. Off by default: it doubles the final render time.
    render_vertical: bool = False
    # true: every video opens with the Cover Founder intro (5 s) and closes with the outro (6 s).
    brand_cards: bool = True
    guest_cover_backfill: bool = True  # on start, give finished videos made earlier a cover that shows the guest
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
    # legacy: slow work (presenter clips, renders) goes straight to the workers, as before. dispatcher: it joins ONE durable line
    # (the work_queue table) and is released first-in-first-out as renderer and presenter-video capacity frees up; waiting never fails.
    progress_cache_s: float = 3.0  # a video's progress is worked out at most this often per project (with the Celery queue); 0 = always fresh
    # AI outreach to distribution outlets (templates, a reply inbox, an agent that answers within approval rules). off = the original one-way email.
    outreach_ai: str = "off"  # off | on
    outreach_reply_domain: str = ""  # replies come back to outreach+<token>@<this domain> (a domain that receives mail); blank = the plain reply-to address
    outreach_inbound_secret: str = ""  # the inbound-mail webhook's secret: a shared secret (X-Inbound-Secret header) or the provider's whsec_ signing secret
    # Send outreach through a mailbox you own (Gmail / Google Workspace: smtp.gmail.com, 587, an app password) instead of the app's usual sender.
    outreach_smtp_host: str = ""  # blank = outreach goes out through the same sender as every other email
    outreach_smtp_port: int = 587  # STARTTLS
    outreach_smtp_user: str = ""
    outreach_smtp_password: str = ""
    outreach_mailbox: str = ""  # that mailbox's address, e.g. outreach@yourdomain.com. Replies come back to outreach+<code>@yourdomain.com (plus-addressing), and it is the From address
    outreach_from_name: str = "Cover Founder"
    outreach_reply_delay_minutes: int = 10  # default: a reply goes out no sooner than this long after the outlet wrote (people do not answer in seconds)
    outreach_new_gap_minutes: int = 3  # default: first emails to outlets are spread at least this far apart
    outreach_new_daily_cap: int = 30  # default: at most this many first emails a day
    outreach_imap_host: str = ""  # alternatively, a mailbox the app reads itself (IMAP over SSL); blank = off
    outreach_imap_port: int = 993
    outreach_imap_user: str = ""
    outreach_imap_password: str = ""
    outreach_imap_folder: str = "INBOX"
    llm_max_concurrency: int = 16  # writing calls in flight at once per process; the rest wait their turn
    llm_retries: int = 2  # a busy or briefly failing writing provider is asked again this many times
    queue_mode: str = "legacy"
    render_queue_slots: int = 0  # renders running at once under the dispatcher; 0 = one per configured renderer x render_jobs_concurrency
    render_jobs_concurrency: int = 1  # heavy renders each renderer runs at once (the same RENDER_JOBS_CONCURRENCY the renderer reads)
    queue_dispatch_grace_s: int = 600  # a released job gets this long to be picked up before it is put back in line
    queue_max_wait_hours: int = 36  # under the dispatcher, a video waiting for a vendor slot is not failed before this
    # Database connections per process (the API, and each worker). Keep (pool_size + max_overflow) x processes under Postgres's
    # max_connections. A request waits up to db_pool_timeout_s for a free connection, then fails fast instead of piling up.
    # With the Celery queue, a worker waits at most this long on a presenter clip, then is released and the same vendor job is polled
    # again shortly. Workers are the scarce thing: without this, each clip in progress would hold one for its whole (minutes-long) wait.
    vendor_hold_s: float = 45.0
    db_pool_size: int = 10
    db_max_overflow: int = 10
    # The same, for each Celery worker process (there are about eleven, and each task opens its own small pool): kept small so the
    # API's connections plus all of the workers' stay under Postgres's max_connections even when every lane is busy.
    db_worker_pool_size: int = 2
    db_worker_max_overflow: int = 3
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
    # Credits: a video costs `credits_per_video` credit (one), whatever the vendors charge; one credit is sold at `usd_per_credit`.
    # Preset purchases get amount / usd_per_credit credits, rounded to 0.01; custom quantities have a $10 minimum.
    bank_transfer_enabled: bool = True  # False hides bank transfer everywhere customers choose how to pay (the code stays; set True to bring it back)
    bank_transfer_review_enabled: bool = True  # New purchases use bank transfer and finance approval; cards are coming soon.
    usd_per_credit: str = "2.70"
    credits_per_video: str = "1"
    credit_purchase_usd: str = "1,10,50,100,200"
    referral_purchase_percent: str = "5"  # the referrer is credited this % of the credits every referred business buys, on every purchase
    referral_signup_credits: str = "0"  # (off) credits the referrer gets when a business they referred signs up; the percentage above replaced it
    hide_free_distribution_outlets: bool = True  # outlets priced at 0 credits are not shown to customers for now; price one in the back office to show it
    credit_markup: str = "0"  # credits taken per 1 USD of vendor cost while a video is made: 0 = none, the video's flat price is its only charge
    low_balance_threshold: str = "1"
    billing_webhook_secret: str = ""  # HMAC secret for payment webhooks; REQUIRED outside local
    nuvion_api_key: str = Field(default="", repr=False)
    nuvion_api_url: str = "https://api.nuvion.dev"
    nuvion_account_id: str = ""
    nuvion_entity_id: str = ""
    nuvion_public_key: str = ""
    nuvion_webhook_secret: str = Field(default="", repr=False)
    # Stripe card payments (hosted Checkout). On when the secret key is set. A test key (sk_test_...) is the sandbox.
    stripe_secret_key: str = Field(default="", repr=False)
    stripe_webhook_secret: str = Field(default="", repr=False)  # whsec_..., signing secret of the /v1/webhooks/stripe endpoint
    stripe_api_url: str = "https://api.stripe.com/v1"  # only changed in local development, to point at a stand-in Stripe
    # Money going back. The code is built and tested but OFF until switched on (then also add the matching events to the Stripe webhook).
    stripe_refunds_enabled: bool = False  # charge.refunded: take back the matching credits
    stripe_chargebacks_enabled: bool = False  # charge.dispute.created / .closed: hold the credits, return them if the dispute is won
    min_fund_usd: str = "10"  # lowest amount that can be added; smaller presets (the $1 test amount) show only in sandbox
    ngn_per_usd: Decimal = Field(default=Decimal("1400"), gt=0, le=1000000, decimal_places=2)
    nuvion_ngn_account_id: str = ""
    nuvion_ngn_card_enabled: bool = False
    nuvion_ngn_bank_enabled: bool = False
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
