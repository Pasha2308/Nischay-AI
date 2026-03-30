"""Persistent run history record (API + registry file)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RunStatus = Literal["running", "success", "failed"]


class RunRecord(BaseModel):
    """One QA run as stored in runs/registry.json."""

    run_id: str
    job_id: str | None = None
    target_url: str
    status: RunStatus = "running"
    start_time: float = Field(..., description="Unix timestamp")
    end_time: float | None = None
    risk_score: int | None = None
    summary: str | None = None
    partial: bool = Field(default=False, description="True if scan ended with partial/timed-out results")
    error: str | None = Field(default=None, description="Failure message when status is failed")
