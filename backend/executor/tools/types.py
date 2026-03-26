"""Shared tool I/O types."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Structured result from any executor tool."""

    ok: bool
    action_type: str
    message: str = ""
    data: dict = Field(default_factory=dict)


EMPTY_REGISTRY_REASON = "unknown_action_type"
