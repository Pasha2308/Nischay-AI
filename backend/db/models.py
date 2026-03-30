"""ORM models for scan persistence."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    pass


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="complete", index=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Shareable snapshot for GET /report/{report_id} (summary, issues, risk_score, delta).
    result_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    defects: Mapped[list["Defect"]] = relationship(
        "Defect", back_populates="scan", cascade="all, delete-orphan"
    )
    risk_snapshots: Mapped[list["RiskSnapshot"]] = relationship(
        "RiskSnapshot", back_populates="scan", cascade="all, delete-orphan"
    )


class Defect(Base):
    __tablename__ = "defects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    issue_type: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(64), nullable=False, default="medium")
    business_impact: Mapped[str] = mapped_column(String(32), nullable=False, default="ux")
    element: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_view: Mapped[str] = mapped_column(Text, nullable=False, default="")
    how_to_fix: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    scan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scan_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)  # list[int]
    screenshot_path: Mapped[str] = mapped_column(Text, nullable=False, default="")

    scan: Mapped["Scan"] = relationship("Scan", back_populates="defects")


class PageFingerprint(Base):
    __tablename__ = "page_fingerprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)
    hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped["Scan"] = relationship("Scan", back_populates="risk_snapshots")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    flows: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # list[str]
    cron_expression: Mapped[str] = mapped_column(String(128), nullable=False, default="0 9 * * 1")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)  # sqlite-friendly bool
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AlertConfig(Base):
    __tablename__ = "alert_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # email|slack|webhook|in_app
    is_enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trigger_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="in_app")
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="", index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IntegrationWaitlist(Base):
    __tablename__ = "integration_waitlist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    integration: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LLMConfig(Base):
    __tablename__ = "llm_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="groq")  # groq|openai|anthropic
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
