"""Selector resolution for tools (no code execution)."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from ..selector_resolver import resolve_selector

logger = logging.getLogger(__name__)


async def effective_selector(
    page: Page,
    selector: str,
    timeout_ms: int,
    action_type: str,
    *,
    smart_resolve: bool,
) -> str:
    if not smart_resolve:
        return selector
    result = await resolve_selector(page, selector, timeout_ms=timeout_ms, action_type=action_type)
    if result.resolved_selector:
        if result.strategy_used != "original":
            logger.info(
                "Smart resolve: '%s' -> '%s' via %s",
                selector,
                result.resolved_selector,
                result.strategy_used,
            )
        return result.resolved_selector
    return selector
