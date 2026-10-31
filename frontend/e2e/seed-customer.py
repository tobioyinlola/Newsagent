"""A non-team test identity in the seeded test workspace. Never run in production."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from sqlalchemy import select
from app.db import session_maker, reset_engine
from app.models import User

async def main():
    async with session_maker()() as db:
        operator = (await db.execute(select(User).where(User.email == "ops@example.com"))).scalar_one()
        db.add(User(email="customer@example.com", role="owner", workspace_id=operator.workspace_id))
        await db.commit()
    await reset_engine()

asyncio.run(main())
