"""PostgreSQL persistence (SQLAlchemy async). Optional when DATABASE_URL is unset."""

from backend.db.config import get_database_url, normalize_database_url
from backend.db.deps import get_db_session
from backend.db.models import Defect, PageFingerprint, RiskSnapshot, Scan
from backend.db.persistence import compute_delta_report, fetch_report_by_id, persist_pipeline_result
from backend.db.session import dispose_engine, get_async_session_maker, init_db_engine

__all__ = [
    "Defect",
    "PageFingerprint",
    "RiskSnapshot",
    "Scan",
    "dispose_engine",
    "get_async_session_maker",
    "get_database_url",
    "get_db_session",
    "init_db_engine",
    "normalize_database_url",
    "persist_pipeline_result",
    "compute_delta_report",
    "fetch_report_by_id",
]
