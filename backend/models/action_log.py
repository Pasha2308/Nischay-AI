"""Structured action trail for pipeline debugging and audit."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

Phase = Literal["crawl", "login", "execute", "analyze"]
ActionType = Literal["navigate", "click", "fill", "submit", "detect", "evaluate"]
Outcome = Literal["success", "failed", "warning", "skipped"]


def should_capture_before_after_pair(action_type: str) -> bool:
    """Whether to take _before and _after screenshots around the action body."""
    return action_type in ("navigate", "click", "submit")


def should_capture_error_after_screenshot(outcome: str) -> bool:
    """After-only capture for failed / warning outcomes (error state)."""
    return outcome in ("failed", "warning")


def mask_sensitive_input(
    description: str,
    target_element: str,
    input_value: str | None,
    action_type: str,
) -> str:
    """Mask password-like values for logging."""
    if not input_value:
        return ""
    combined = f"{description} {target_element}".lower()
    if action_type in ("fill", "submit") and (
        "password" in combined
        or "pass" in combined
        or "passwd" in combined
        or "[type=\"password\"]" in combined
        or "type=password" in combined
    ):
        return "***"
    return input_value


@dataclass
class ActionRecord:
    id: str
    timestamp: str
    phase: str
    action_type: str
    description: str
    target_url: str
    target_element: str
    input_value: str
    outcome: str
    outcome_detail: str
    screenshot_path_before: str
    screenshot_path_after: str
    duration_ms: int
    defect_triggered: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Backward compatibility for consumers expecting a single path
        d["screenshot_path"] = self.screenshot_path_after or self.screenshot_path_before
        return d


def new_action_record(
    *,
    phase: str,
    action_type: str,
    description: str,
    target_url: str = "",
    target_element: str = "",
    input_value: str | None = None,
    outcome: str = "success",
    outcome_detail: str = "",
    screenshot_path_before: str = "",
    screenshot_path_after: str = "",
    duration_ms: int = 0,
    defect_triggered: str | None = None,
    action_id: str | None = None,
) -> ActionRecord:
    masked = mask_sensitive_input(description, target_element, input_value, action_type)
    return ActionRecord(
        id=action_id or str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        phase=phase,
        action_type=action_type,
        description=description,
        target_url=target_url or "",
        target_element=target_element or "",
        input_value=masked,
        outcome=outcome,
        outcome_detail=outcome_detail or "",
        screenshot_path_before=screenshot_path_before or "",
        screenshot_path_after=screenshot_path_after or "",
        duration_ms=int(duration_ms),
        defect_triggered=defect_triggered,
    )
