"""Playwright helpers.

This repo previously referenced a more sophisticated stealth layer. For now we
provide a small, dependency-free wrapper that keeps modules runnable.
"""

from __future__ import annotations

import random
from typing import Any


async def create_stealth_context(
    browser: Any,
    viewport: dict[str, int] | None = None,
    user_agent: str | None = None,
    storage_state: dict | None = None,
    record_video_dir: str | None = None,
):
    """Create a browser context with optional storage state and video."""
    kwargs: dict[str, object] = {}
    kwargs["no_viewport"] = True
    if viewport and not kwargs.get("no_viewport"):
        kwargs["viewport"] = viewport
    if user_agent:
        kwargs["user_agent"] = user_agent
    if storage_state:
        kwargs["storage_state"] = storage_state
    if record_video_dir:
        kwargs["record_video_dir"] = record_video_dir
    return await browser.new_context(**kwargs)


async def human_delay(page: Any, min_ms: int = 250, max_ms: int = 900) -> None:
    """Small randomized delay to reduce flakiness when crawling."""
    ms = random.randint(min_ms, max_ms)
    await page.wait_for_timeout(ms)

