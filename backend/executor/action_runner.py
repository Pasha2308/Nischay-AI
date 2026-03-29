"""Action runner — dispatches Action models through the tool registry."""

from __future__ import annotations

import logging
import re
import time

from playwright.async_api import Page

from shared.models.test_plan import Action

from .tools.runner import ToolContext, execute_action_or_raise

logger = logging.getLogger(__name__)

# Dynamic variables that can appear in action values (Postman-style).
_DYNAMIC_VAR_RE = re.compile(r"\{\{\$(\w+)\}\}")


def _build_dynamic_vars() -> dict[str, str]:
    """Build a snapshot of dynamic variable values (fixed for one test case)."""
    return {
        "timestamp": str(int(time.time())),
    }


def _resolve_dynamic_vars(value: str, resolved: dict[str, str]) -> str:
    """Replace ``{{$variable}}`` tokens with pre-computed values."""

    def _replacer(match: re.Match) -> str:
        name = match.group(1)
        if name in resolved:
            return resolved[name]
        logger.warning("Unknown dynamic variable: {{$%s}}", name)
        return match.group(0)

    return _DYNAMIC_VAR_RE.sub(_replacer, value)


def resolve_dynamic_vars_for_test_case(actions: list[Action]) -> None:
    """Resolve all ``{{$variable}}`` tokens in a list of actions in-place.

    A single snapshot of dynamic values is used so that the same
    ``{{$timestamp}}`` value appears in every action (e.g. a vault
    created in preconditions and referenced again in test steps).
    """
    resolved = _build_dynamic_vars()
    for action in actions:
        if action.value and _DYNAMIC_VAR_RE.search(action.value):
            action.value = _resolve_dynamic_vars(action.value, resolved)


async def run_action(
    page: Page,
    action: Action,
    timeout: int = 6000,
    smart_resolve: bool = True,
) -> None:
    """Execute a single action via the tool registry.

    Args:
        page: Playwright page instance.
        action: The action to execute.
        timeout: Selector timeout in milliseconds (default 6000).
        smart_resolve: When True, try alternative selectors before failing.
    """

    logger.debug(
        "Running action: %s | selector=%s | value=%s | %s",
        action.action_type,
        action.selector,
        action.value,
        action.description or "",
    )

    ctx = ToolContext(timeout_ms=timeout, smart_resolve=smart_resolve)
    await execute_action_or_raise(page, action, ctx)
