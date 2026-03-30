"""Navigation-oriented tools: goto URL, click, hover."""

# ADD THIS — Run-wide screenshots for API-triggered flows are captured in
# ``backend.orchestrator.Orchestrator._execute`` (``ScreenshotManager`` under
# ``runs/<run_id>/screenshots/``). This module performs navigation only.
# END ADD THIS

from __future__ import annotations

import logging
from playwright.async_api import Page
from pydantic import BaseModel, Field

from shared.models.test_plan import Action
from shared.utils.browser_stealth import human_delay

from .resolve import effective_selector
from .types import ToolResult

logger = logging.getLogger(__name__)


class NavigateInput(BaseModel):
    url: str = Field(..., min_length=1, description="Absolute or relative URL to open")


class NavigateOutput(BaseModel):
    final_url: str = ""


class ClickInput(BaseModel):
    selector: str = Field(..., min_length=1)


class HoverInput(BaseModel):
    selector: str = Field(..., min_length=1)


def navigate_input_from_action(action: Action) -> NavigateInput:
    url = (action.value or action.selector or "").strip()
    if not url:
        raise ValueError("navigate requires url in value or selector")
    return NavigateInput(url=url)


async def run_navigate(
    page: Page,
    inp: NavigateInput,
    *,
    timeout_ms: int,
) -> ToolResult:
    logger.debug("Navigating to %s", inp.url)
    await page.goto(inp.url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10_000))
    except Exception:
        pass
    return ToolResult(
        ok=True,
        action_type="navigate",
        message="Navigation complete",
        data=NavigateOutput(final_url=page.url).model_dump(),
    )


def click_input_from_action(action: Action) -> ClickInput:
    if not action.selector:
        raise ValueError("click requires selector")
    return ClickInput(selector=action.selector)


async def run_click(
    page: Page,
    inp: ClickInput,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    await human_delay(page, min_ms=50, max_ms=250)
    effective = await effective_selector(
        page, inp.selector, timeout_ms, "click", smart_resolve=smart_resolve
    )
    logger.debug("Clicking: %s", effective)
    await page.click(effective, timeout=timeout_ms)
    return ToolResult(ok=True, action_type="click", message=f"Clicked {effective}", data={"selector": effective})


def hover_input_from_action(action: Action) -> HoverInput:
    if not action.selector:
        raise ValueError("hover requires selector")
    return HoverInput(selector=action.selector)


async def run_hover(
    page: Page,
    inp: HoverInput,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    await human_delay(page, min_ms=30, max_ms=150)
    effective = await effective_selector(
        page, inp.selector, timeout_ms, "hover", smart_resolve=smart_resolve
    )
    logger.debug("Hovering: %s", effective)
    await page.hover(effective, timeout=timeout_ms)
    return ToolResult(ok=True, action_type="hover", message=f"Hovered {effective}", data={"selector": effective})


async def handle_navigate_action(
    page: Page,
    action: Action,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    del smart_resolve
    inp = navigate_input_from_action(action)
    return await run_navigate(page, inp, timeout_ms=timeout_ms)


async def handle_click_action(
    page: Page,
    action: Action,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    inp = click_input_from_action(action)
    return await run_click(
        page, inp, timeout_ms=timeout_ms, smart_resolve=smart_resolve
    )


async def handle_hover_action(
    page: Page,
    action: Action,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    inp = hover_input_from_action(action)
    return await run_hover(
        page, inp, timeout_ms=timeout_ms, smart_resolve=smart_resolve
    )
