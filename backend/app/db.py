from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine = None
_maker: async_sessionmaker[AsyncSession] | None = None
_worker_pool = False  # True in a Celery worker process: it gets the smaller pool (see config.db_worker_pool_size)


def use_worker_pool() -> None:
    """Called once when a Celery worker process starts: its database pools are the small worker size from then on."""
    global _worker_pool
    _worker_pool = True


def session_maker() -> async_sessionmaker[AsyncSession]:
    global _engine, _maker
    if _maker is None:
        s = get_settings()
        opts: dict = {"pool_pre_ping": True}
        if not s.database_url.startswith("sqlite"):  # SQLite (local tests) has no real pool to size
            opts.update(
                pool_size=s.db_worker_pool_size if _worker_pool else s.db_pool_size,
                max_overflow=s.db_worker_max_overflow if _worker_pool else s.db_max_overflow,
                pool_timeout=s.db_pool_timeout_s,
                pool_recycle=s.db_pool_recycle_s,
            )
        _engine = create_async_engine(s.database_url, **opts)
        _maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _maker


def set_session_maker(maker: async_sessionmaker[AsyncSession]) -> None:
    """Used by tests to swap in an in-memory database."""
    global _maker
    _maker = maker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_maker()() as session:
        yield session


async def release_connection(session: AsyncSession) -> None:
    """Give the pooled database connection back before a slow call to another service (an AI writer, a vendor).

    A request's session keeps its connection from its first query until it commits, and the pool is small (it is shared by every
    request), so a request that waits a minute on an AI model would hold one of the few connections for that minute. Does
    nothing if there are unsaved changes: committing those early could keep half of an operation that should be all-or-nothing.
    Objects already loaded stay usable (sessions here use expire_on_commit=False) and the next query takes a fresh connection."""
    if session.new or session.dirty or session.deleted:
        return
    await session.commit()


async def reset_engine() -> None:
    """Dispose the engine. Celery runs each task in a fresh event loop, and asyncpg connections are loop-bound."""
    global _engine, _maker
    if _engine is not None:
        await _engine.dispose()
    _engine = _maker = None
