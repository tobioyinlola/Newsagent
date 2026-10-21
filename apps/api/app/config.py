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
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://newsagent:newsagent@localhost:5432/newsagent"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""
    heygen_api_key: str = ""
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
    auth_issuer: str = ""
    auth_audience: str = ""
    sentry_dsn: str = ""
    app_base_url: str = "http://localhost:5173"
    environment: str = "local"  # local, staging, production
    use_mocks: bool = True
    operator_emails: str = ""  # comma separated; may call /admin
    queue_backend: str = "inline"  # inline | celery
    rate_limit_backend: str = ""  # "memory" | "redis"; default: redis outside local
    trust_proxy_headers: bool = False  # True behind Railway/Cloudflare so X-Forwarded-For identifies clients
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
