"""Low-level browser / page tools: wait, scroll, keyboard, screenshot placeholder."""

from __future__ import annotations

import logging
import re

from playwright.async_api import Page
from pydantic import BaseModel, Field

from shared.models.test_plan import Action

from .resolve import effective_selector
from .types import ToolResult

logger = logging.getLogger(__name__)

# Only allow integer Y offset for scroll-to-Y (no arbitrary JS)
_SCROLL_Y_RE = re.compile(r"^-?\d+$")


class KeyboardInput(BaseModel):
    key: str = Field(default="Enter", min_length=1)


class WaitForSelectorInput(BaseModel):
    selector: str = Field(..., min_length=1)


class WaitMsInput(BaseModel):
    milliseconds: int = Field(..., ge=0, le=120_000)


class ScrollYInput(BaseModel):
    y_pixel: int


class ScrollElementInput(BaseModel):
    selector: str = Field(..., min_length=1)


class ScreenshotInput(BaseModel):
    """No fields — screenshots are taken by EvidenceCollector around steps."""


async def run_keyboard(page: Page, inp: KeyboardInput, *, timeout_ms: int) -> ToolResult:
    del timeout_ms
    logger.debug("Pressing key: %s", inp.key)
    await page.keyboard.press(inp.key)
    return ToolResult(ok=True, action_type="keyboard", message=f"Pressed {inp.key}", data={"key": inp.key})


async def run_wait_selector(
    page: Page, inp: WaitForSelectorInput, *, timeout_ms: int, smart_resolve: bool
) -> ToolResult:
    effective = await effective_selector(
        page, inp.selector, timeout_ms, "wait", smart_resolve=smart_resolve
    )
    logger.debug("Waiting for selector: %s", effective)
    await page.wait_for_selector(effective, timeout=timeout_ms)
    return ToolResult(ok=True, action_type="wait", message=f"Found {effective}", data={"selector": effective})


async def run_wait_ms(page: Page, inp: WaitMsInput) -> ToolResult:
    logger.debug("Waiting %sms", inp.milliseconds)
    await page.wait_for_timeout(inp.milliseconds)
    return ToolResult(
        ok=True,
        action_type="wait",
        message=f"Waited {inp.milliseconds}ms",
        data={"milliseconds": inp.milliseconds},
    )


async def run_scroll_y(page: Page, inp: ScrollYInput) -> ToolResult:
    await page.evaluate("(y) => window.scrollTo(0, y)", inp.y_pixel)
    return ToolResult(
        ok=True,
        action_type="scroll",
        message=f"Scrolled to y={inp.y_pixel}",
        data={"y": inp.y_pixel},
    )


async def run_scroll_bottom(page: Page) -> ToolResult:
    await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    return ToolResult(ok=True, action_type="scroll", message="Scrolled to bottom", data={"mode": "bottom"})


async def run_scroll_element(page: Page, inp: ScrollElementInput, *, timeout_ms: int) -> ToolResult:
    loc = page.locator(inp.selector).first
    await loc.scroll_into_view_if_needed(timeout=timeout_ms)
    return ToolResult(
        ok=True,
        action_type="scroll",
        message=f"Scrolled into view: {inp.selector}",
        data={"selector": inp.selector},
    )


async def run_screenshot_placeholder(_inp: ScreenshotInput) -> ToolResult:
    logger.debug("screenshot action — captured by evidence collector")
    return ToolResult(ok=True, action_type="screenshot", message="noop — handled by collector", data={})


def keyboard_input_from_action(action: Action) -> KeyboardInput:
    return KeyboardInput(key=action.value or "Enter")


async def handle_keyboard_action(
    page: Page, action: Action, *, timeout_ms: int, smart_resolve: bool
) -> ToolResult:
    del smart_resolve
    return await run_keyboard(page, keyboard_input_from_action(action), timeout_ms=timeout_ms)


async def handle_wait_action(
    page: Page, action: Action, *, timeout_ms: int, smart_resolve: bool
) -> ToolResult:
    if action.selector:
        return await run_wait_selector(
            page, WaitForSelectorInput(selector=action.selector), timeout_ms=timeout_ms, smart_resolve=smart_resolve
        )
    if action.value and action.value.strip().isdigit():
        return await run_wait_ms(page, WaitMsInput(milliseconds=int(action.value)))
    return await run_wait_ms(page, WaitMsInput(milliseconds=1000))


async def handle_scroll_action(
    page: Page, action: Action, *, timeout_ms: int, smart_resolve: bool
) -> ToolResult:
    del smart_resolve
    if action.value and _SCROLL_Y_RE.match(action.value.strip()):
        return await run_scroll_y(page, ScrollYInput(y_pixel=int(action.value.strip())))
    if action.selector:
        return await run_scroll_element(
            page, ScrollElementInput(selector=action.selector), timeout_ms=timeout_ms
        )
    return await run_scroll_bottom(page)


async def handle_screenshot_action(
    page: Page, action: Action, *, timeout_ms: int, smart_resolve: bool
) -> ToolResult:
    del page, action, timeout_ms, smart_resolve
    return await run_screenshot_placeholder(ScreenshotInput())
