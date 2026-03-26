"""Read-only DOM extraction tools (safe — no script execution from plan text)."""

from __future__ import annotations

import logging
from typing import Optional

from playwright.async_api import Page
from pydantic import BaseModel, Field

from shared.models.test_plan import Action

from .resolve import effective_selector
from .types import ToolResult

logger = logging.getLogger(__name__)

_MAX_TEXT_LEN = 50_000


class ExtractTextInput(BaseModel):
    """If selector is None, reads document body text."""

    selector: Optional[str] = None


class ExtractTextOutput(BaseModel):
    text: str
    truncated: bool = False


class ExtractAttributeInput(BaseModel):
    selector: str = Field(..., min_length=1)
    attribute_name: str = Field(..., min_length=1, description="HTML attribute, e.g. href, value")


class ExtractAttributeOutput(BaseModel):
    value: str


def extract_text_input_from_action(action: Action) -> ExtractTextInput:
    sel = (action.selector or "").strip() or None
    return ExtractTextInput(selector=sel)


def extract_attribute_input_from_action(action: Action) -> ExtractAttributeInput:
    if not action.selector:
        raise ValueError("extract_attribute requires selector (element)")
    # value holds attribute name (e.g. href, value, data-testid)
    attr = (action.value or "").strip()
    if not attr:
        raise ValueError("extract_attribute requires expected_value or value as attribute name")
    return ExtractAttributeInput(selector=action.selector, attribute_name=attr)


async def run_extract_text(
    page: Page,
    inp: ExtractTextInput,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    if inp.selector:
        effective = await effective_selector(
            page, inp.selector, timeout_ms, "extract_text", smart_resolve=smart_resolve
        )
        el = await page.wait_for_selector(effective, timeout=timeout_ms)
        raw = (await el.text_content()) or ""
    else:
        raw = (await page.text_content("body")) or ""

    truncated = len(raw) > _MAX_TEXT_LEN
    text = raw[:_MAX_TEXT_LEN] if truncated else raw
    out = ExtractTextOutput(text=text, truncated=truncated)
    logger.debug("extract_text: %d chars (truncated=%s)", len(text), truncated)
    return ToolResult(
        ok=True,
        action_type="extract_text",
        message="Text extracted",
        data=out.model_dump(),
    )


async def run_extract_attribute(
    page: Page,
    inp: ExtractAttributeInput,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    effective = await effective_selector(
        page, inp.selector, timeout_ms, "extract_attribute", smart_resolve=smart_resolve
    )
    el = await page.wait_for_selector(effective, timeout=timeout_ms)
    val = await el.get_attribute(inp.attribute_name)
    out = ExtractAttributeOutput(value=val or "")
    return ToolResult(
        ok=True,
        action_type="extract_attribute",
        message=f"Attribute {inp.attribute_name!r} read",
        data=out.model_dump(),
    )


async def handle_extract_text_action(
    page: Page, action: Action, *, timeout_ms: int, smart_resolve: bool
) -> ToolResult:
    inp = extract_text_input_from_action(action)
    return await run_extract_text(page, inp, timeout_ms=timeout_ms, smart_resolve=smart_resolve)


async def handle_extract_attribute_action(
    page: Page, action: Action, *, timeout_ms: int, smart_resolve: bool
) -> ToolResult:
    inp = extract_attribute_input_from_action(action)
    return await run_extract_attribute(page, inp, timeout_ms=timeout_ms, smart_resolve=smart_resolve)
