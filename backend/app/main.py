import json
import logging
import re

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routes import (
    account,
    admin,
    auth,
    backoffice,
    billing,
    brand,
    broll,
    delivery,
    guest,
    health,
    interview,
    ops,
    presenter,
    projects,
    system,
)
from app.runtime_checks import assert_runtime_ok

# Magic-link and share tokens are credentials. They live in URL paths, so scrub them from every log line.
_TOKEN_PATH = re.compile(r"(/v1/(?:interview|share)/)[^/\s?\"']+")


def redact(text: str) -> str:
    return _TOKEN_PATH.sub(r"\1[redacted]", text)


class RedactTokens(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if isinstance(record.args, tuple):
            # args can be non-str objects (httpx.URL, bytes...) whose text still contains the path
            record.args = tuple(redact(str(a)) if (isinstance(a, str) or "/v1/" in str(a)) else a for a in record.args)
        return True


def _scrub_sentry(event, _hint):
    req = event.get("request") or {}
    if "url" in req:
        req["url"] = redact(req["url"])
    if event.get("transaction"):
        event["transaction"] = redact(event["transaction"])
    return event


CORRELATION_FIELDS = (
    "project_id",
    "job_id",
    "stage",
    "provider",
    "vendor_id",
    "slot",
    "attempt",
    "category",
    "duration_s",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        doc = {"level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        for k in CORRELATION_FIELDS:  # who/what a line is about, for tracing one video through the pipeline
            if hasattr(record, k):
                doc[k] = getattr(record, k)
        return json.dumps(doc, default=str)


def create_app() -> FastAPI:
    s = get_settings()
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    assert_runtime_ok(s)  # staging/production only; local is exempt
    h.addFilter(RedactTokens())
    logging.basicConfig(level=logging.INFO, handlers=[h], force=True)
    for name in ("uvicorn.access", "httpx"):
        logging.getLogger(name).addFilter(RedactTokens())
    if s.sentry_dsn:
        sentry_sdk.init(dsn=s.sentry_dsn, environment=s.environment, before_send=_scrub_sentry, send_default_pii=False)
    app = FastAPI(title="Newsagent API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=[s.app_base_url, s.admin_base_url], allow_methods=["*"], allow_headers=["*"]
    )
    if s.is_local and s.use_mocks:
        from app.routes import devmail, devstorage

        app.include_router(devstorage.router)
        app.include_router(devmail.router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # The back office is its own app. A page served by the CUSTOMER app must never be able to call it, even
        # with an operator's session: refuse any /v1/admin request that comes from the customer app's origin.
        if (
            request.url.path.startswith("/v1/admin")
            and request.headers.get("origin") == s.app_base_url
            and s.app_base_url != s.admin_base_url
        ):
            return JSONResponse({"detail": "The back office is not available from this app."}, status_code=403)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/v1/") and not request.url.path.startswith("/v1/dev-storage"):
            resp.headers.setdefault(
                "Cache-Control", "no-store"
            )  # tokens, signed URLs and personal data must not be cached
        if not s.is_local:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    for r in (
        health.router,
        auth.router,
        brand.router,
        broll.router,
        billing.router,
        projects.router,
        delivery.router,
        interview.router,
        guest.router,
        admin.router,
        backoffice.router,
        presenter.router,
        system.router,
        account.router,
        ops.router,
    ):
        app.include_router(r)
    return app


app = create_app()
