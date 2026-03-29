"""Async engine and session factory."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from backend.db.base import Base
from backend.db.config import get_database_url, normalize_database_url

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def init_db_engine() -> AsyncEngine | None:
    """Create (or return cached) async engine. Returns None if DATABASE_URL is unset."""
    global _engine, _session_maker
    if _engine is not None:
        return _engine
    url = get_database_url()
    if not url:
        return None
    try:
        async_url = normalize_database_url(url)
        _engine = create_async_engine(async_url, echo=False, pool_pre_ping=True)
        _session_maker = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    except Exception as e:
        logger.warning("Database engine init failed (%s); persistence disabled.", e)
        _engine = None
        _session_maker = None
    return _engine


def get_async_session_maker() -> async_sessionmaker[AsyncSession] | None:
    """Return session factory for dependency injection / manual use."""
    init_db_engine()
    return _session_maker


async def ensure_schema(engine: AsyncEngine) -> None:
    """Create tables if they do not exist (dev-friendly; use Alembic in production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose engine on shutdown."""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None
