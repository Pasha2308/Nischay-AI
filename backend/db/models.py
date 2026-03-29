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
    severity: Mapped[str] = mapped_column(String(64), nullable=False, default="medium")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

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
