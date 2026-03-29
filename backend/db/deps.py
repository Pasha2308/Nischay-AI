"""FastAPI / app-layer database session helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_async_session_maker


async def get_db_session() -> AsyncGenerator[AsyncSession | None, None]:
    """
    Yield an async SQLAlchemy session, or None if DATABASE_URL is not configured.
    Commits on success; rolls back on exception.
    """
    maker = get_async_session_maker()
    if maker is None:
        yield None
        return
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
