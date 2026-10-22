"""Fill a database with realistic data using the real API and mocked vendors (for restore and load tests).

  DATABASE_URL=postgresql+asyncpg://... uv run --project apps/api python scripts/seed_demo.py [N_PROJECTS]
The schema must already exist (alembic upgrade head). Never run against production.
"""

import asyncio
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

os.environ.update(ENVIRONMENT="local", USE_MOCKS="true", QUEUE_BACKEND="inline", OPERATOR_EMAILS="ops@example.com")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

import httpx  # noqa: E402

from app.cli import bootstrap_operator  # noqa: E402
from app.db import reset_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.pipeline.queue import get_queue  # noqa: E402
from app.services import ratelimit  # noqa: E402

OPS = {"Authorization": "Bearer dev:ops@example.com"}


async def main(n: int) -> None:
    await bootstrap_operator("ops@example.com", Decimal("0"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://seed") as c:
        for vendor in ("mock", "renderer", "transcription"):
            await c.put("/v1/admin/vendor-budgets", json={"vendor": vendor, "limit": "100000"}, headers=OPS)
        inv = (await c.post("/v1/admin/invites", json={"email": "seed@startup.example.com", "workspace_name": "Seed Co", "credits": "100000", "spend_cap": "100000"}, headers=OPS)).json()
        owner = {"Authorization": "Bearer dev:seed@startup.example.com"}
        await c.post("/v1/auth/signup/start", json={"invite_code": inv["code"], "password": "seed-password-123"})
        mail = (await c.get("/v1/dev/last-email", params={"to": "seed@startup.example.com"})).json()["text"]
        code = re.search(r"\b(\d{6})\b", mail).group(1)  # type: ignore[union-attr]
        await c.post("/v1/auth/signup/verify", json={"invite_code": inv["code"], "code": code})
        await c.patch(f"/v1/admin/workspaces/{inv['workspace_id']}", json={"max_videos_per_day": 10000}, headers=OPS)
        for i in range(n):
            ratelimit.reset()  # the seeder is a trusted batch, not a user
            pid = (await c.post("/v1/projects", json={"brief_text": f"Startup number {i} helps farmers sell produce online across West Africa."}, headers=owner)).json()["id"]
            s = (await c.post(f"/v1/projects/{pid}/script/generate", headers=owner)).json()
            body = {k: s[k] for k in ("ticker_lines", "lower_thirds", "interview_questions")}
            body["segments"] = [{"kind": "intro", "text": f"Tonight we feature startup number {i}."}]
            await c.put(f"/v1/projects/{pid}/script", json=body, headers=owner)
            await c.post(f"/v1/projects/{pid}/script/approve", headers=owner)
            await get_queue().drain()
    await reset_engine()
    print(f"seeded {n} projects")


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 5))
