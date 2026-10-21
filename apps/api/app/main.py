import json
import logging

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import admin, auth, brand, delivery, health, projects


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"level": record.levelname, "logger": record.name, "msg": record.getMessage()})


def create_app() -> FastAPI:
    s = get_settings()
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[h], force=True)
    if s.sentry_dsn:
        sentry_sdk.init(dsn=s.sentry_dsn, environment=s.environment)
    app = FastAPI(title="Newsagent API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=[s.app_base_url], allow_methods=["*"], allow_headers=["*"])
    if s.is_local and s.use_mocks:
        from app.routes import devstorage

        app.include_router(devstorage.router)
    for r in (health.router, auth.router, brand.router, projects.router, delivery.router, admin.router):
        app.include_router(r)
    return app


app = create_app()
