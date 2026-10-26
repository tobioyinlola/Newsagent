import os

os.environ.update(ENVIRONMENT="local", USE_MOCKS="true", OPERATOR_EMAILS="ops@example.com", REQUIRE_INTERVIEW="false")

from decimal import Decimal  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app import db  # noqa: E402
from app.integrations import registry  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User, Workspace  # noqa: E402
from app.pipeline import runner  # noqa: E402
from app.pipeline.queue import InlineQueue, set_queue  # noqa: E402
from app.services import ledger, ratelimit  # noqa: E402
from app.services.spend_guard import ensure_vendor_budget  # noqa: E402


@pytest.fixture
async def maker(tmp_path):
    # TEST_DATABASE_URL (e.g. postgresql+asyncpg://...) runs the suite on Postgres; default is SQLite.
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/t.db"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    m = async_sessionmaker(engine, expire_on_commit=False)
    db.set_session_maker(m)
    registry.reset_providers()
    ratelimit.reset()
    runner.BACKOFF_SCALE = 0
    q = InlineQueue()
    set_queue(q)
    yield m
    await engine.dispose()


@pytest.fixture
async def workspace(maker):
    async with maker() as s:
        ws = Workspace(name="Acme", credit_balance=Decimal("0"), spend_cap=Decimal("50"))
        s.add(ws)
        await s.flush()
        await ledger.apply(s, ws, Decimal("10"), "grant", description="test credits")
        s.add(User(email="owner@acme.test", workspace_id=ws.id))
        s.add(User(email="ops@example.com", workspace_id=ws.id))
        for vendor in ("mock", "heygen", "synthesia", "renderer", "transcription"):
            await ensure_vendor_budget(s, vendor, Decimal("100"))
        await s.commit()
        return ws.id


@pytest.fixture
async def client(maker):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


OWNER = {"Authorization": "Bearer dev:owner@acme.test"}
OPS = {"Authorization": "Bearer dev:ops@example.com"}
