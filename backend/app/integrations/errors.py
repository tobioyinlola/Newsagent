"""One vocabulary for why a vendor call failed, so the pipeline retries what is worth retrying and nothing else."""

import asyncio
from dataclasses import dataclass

import httpx

# category -> retry? ("permanent" ones fail fast: another attempt cannot succeed and may cost money)
RETRYABLE = {"rate_limited": True, "temporary": True, "timeout": True, "busy": True}
CATEGORIES = ("invalid_input", "auth", "rate_limited", "temporary", "timeout", "busy", "storage", "render", "unknown")
MAX_RETRY_AFTER_S = 120.0


class ProviderError(Exception):
    """A vendor failure with a category. `retry_after` is the vendor's own hint in seconds."""

    user_message: str | None = None  # what the owner should read, when the generic wording would mislead

    def __init__(self, message: str, category: str = "unknown", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.category, self.retry_after = category, retry_after

    @property
    def retryable(self) -> bool:
        return RETRYABLE.get(self.category, self.category in {"unknown", "storage", "render"})


class ProviderPending(ProviderError):
    """The vendor is still working (e.g. a long avatar render). Nothing failed: resume polling the same request."""

    def __init__(self, message: str = "The vendor is still rendering") -> None:
        super().__init__(message, "timeout")


class Deferred(ProviderPending):
    """Still working, and this worker has waited long enough: let it go and poll the same vendor job again shortly. Nothing failed
    and no attempt is used; the job simply goes back in line."""

    def __init__(self, resume_after: float = 20.0) -> None:
        super().__init__("The vendor is still rendering; checking again shortly")
        self.resume_after = resume_after


@dataclass(frozen=True)
class Classified:
    category: str
    retryable: bool
    retry_after: float | None
    message: str


def _retry_after(r: httpx.Response) -> float | None:
    try:
        return min(float(r.headers.get("retry-after", "")), MAX_RETRY_AFTER_S)
    except ValueError:
        return None


def classify(exc: BaseException) -> Classified:
    """Decide how to treat an exception raised by a vendor adapter."""
    if isinstance(exc, ProviderError):
        return Classified(exc.category, exc.retryable, exc.retry_after, str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return Classified("auth", False, None, f"The provider rejected our credentials ({code}).")
        if code == 429:
            return Classified("rate_limited", True, _retry_after(exc.response), "The provider is rate limiting us.")
        if code in (408, 425) or code >= 500:
            return Classified("temporary", True, _retry_after(exc.response), f"The provider had a problem ({code}).")
        return Classified("invalid_input", False, None, f"The provider refused the request ({code}).")
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError)):
        return Classified("timeout", True, None, "The provider took too long to answer.")
    if isinstance(exc, (httpx.TransportError, ConnectionError)):
        return Classified("temporary", True, None, "We couldn't reach the provider.")
    return Classified("unknown", True, None, str(exc)[:300] or exc.__class__.__name__)
