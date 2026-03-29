"""Single Playwright browser launch helper — used by orchestrator, crawler, executor."""

from __future__ import annotations

from typing import Literal

from playwright.async_api import Browser, Playwright

BrowserTypeName = Literal["chromium", "firefox", "webkit"]

_CHROMIUM_ARGS = (
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
)


async def launch_browser(
    playwright: Playwright,
    *,
    browser_type: BrowserTypeName = "chromium",
    requires_login: bool = False,
) -> Browser:
    """Launch a Playwright browser. Chromium keeps existing stealth-oriented args; other engines use the same timing only."""
    _ = requires_login  # reserved for future headful / policy tweaks
    print("🚀 PLAYWRIGHT LAUNCH TRIGGERED", flush=True)
    common: dict = {"headless": False, "slow_mo": 80}
    if browser_type == "firefox":
        return await playwright.firefox.launch(**common)
    if browser_type == "webkit":
        return await playwright.webkit.launch(**common)
    return await playwright.chromium.launch(**common, args=list(_CHROMIUM_ARGS))
