"""Async callback type for pipeline observability (orchestrator, crawler, executor)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

PipelineEmit = Callable[[str, str, dict[str, Any] | None], Awaitable[None]]
