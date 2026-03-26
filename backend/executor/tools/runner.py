"""Dispatch Action models to registered tools."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from playwright.async_api import Page

from shared.models.test_plan import Action

from .registry import TOOL_REGISTRY
from .types import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    timeout_ms: int = 10_000
    smart_resolve: bool = True


async def execute_action(page: Page, action: Action, ctx: ToolContext) -> ToolResult:
    """Run the tool registered for ``action.action_type``.

    Returns a structured ``ToolResult``. Does not raise for unknown actions
    (``ok=False``); use ``execute_action_or_raise`` when Playwright-style
    failure propagation is desired.
    """
    handler = TOOL_REGISTRY.get(action.action_type)
    if handler is None:
        msg = f"No tool registered for action_type={action.action_type!r}"
        logger.warning(msg)
        return ToolResult(
            ok=False,
            action_type=action.action_type,
            message=msg,
            data={"reason": "unknown_action_type"},
        )

    try:
        return await handler(
            page,
            action,
            timeout_ms=ctx.timeout_ms,
            smart_resolve=ctx.smart_resolve,
        )
    except Exception as e:
        logger.debug("Tool error [%s]: %s", action.action_type, e)
        return ToolResult(
            ok=False,
            action_type=action.action_type,
            message=str(e),
            data={"error_type": type(e).__name__},
        )


async def execute_action_or_raise(page: Page, action: Action, ctx: ToolContext) -> ToolResult:
    """Execute tool and raise if the tool reports failure or raises."""
    result = await execute_action(page, action, ctx)
    if not result.ok:
        raise RuntimeError(result.message or "tool failed")
    return result
