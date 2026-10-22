import json
import logging
import re

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import admin, auth, brand, delivery, guest, health, interview, projects

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


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"level": record.levelname, "logger": record.name, "msg": record.getMessage()})


def create_app() -> FastAPI:
    s = get_settings()
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    h.addFilter(RedactTokens())
    logging.basicConfig(level=logging.INFO, handlers=[h], force=True)
    for name in ("uvicorn.access", "httpx"):
        logging.getLogger(name).addFilter(RedactTokens())
    if s.sentry_dsn:
        sentry_sdk.init(dsn=s.sentry_dsn, environment=s.environment, before_send=_scrub_sentry, send_default_pii=False)
    app = FastAPI(title="Newsagent API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=[s.app_base_url], allow_methods=["*"], allow_headers=["*"])
    if s.is_local and s.use_mocks:
        from app.routes import devstorage

        app.include_router(devstorage.router)
    for r in (
        health.router,
        auth.router,
        brand.router,
        projects.router,
        delivery.router,
        interview.router,
        guest.router,
        admin.router,
    ):
        app.include_router(r)
    return app


app = create_app()
