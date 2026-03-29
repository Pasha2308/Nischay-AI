"""Database connection settings (environment-driven)."""

from __future__ import annotations

import os


def get_database_url() -> str | None:
    """Return async PostgreSQL URL if configured, else None."""
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    return raw or None


def normalize_database_url(url: str) -> str:
    """Ensure SQLAlchemy async driver prefix for PostgreSQL."""
    u = url.strip()
    if u.startswith("postgresql+asyncpg://"):
        return u
    if u.startswith("postgres://"):
        return "postgresql+asyncpg://" + u[len("postgres://") :]
    if u.startswith("postgresql://"):
        return "postgresql+asyncpg://" + u[len("postgresql://") :]
    return u
