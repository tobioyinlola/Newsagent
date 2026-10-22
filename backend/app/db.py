from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine = None
_maker: async_sessionmaker[AsyncSession] | None = None


def session_maker() -> async_sessionmaker[AsyncSession]:
    global _engine, _maker
    if _maker is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        _maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _maker


def set_session_maker(maker: async_sessionmaker[AsyncSession]) -> None:
    """Used by tests to swap in an in-memory database."""
    global _maker
    _maker = maker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_maker()() as session:
        yield session


async def reset_engine() -> None:
    """Dispose the engine. Celery runs each task in a fresh event loop, and asyncpg connections are loop-bound."""
    global _engine, _maker
    if _engine is not None:
        await _engine.dispose()
    _engine = _maker = None
