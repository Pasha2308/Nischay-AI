"""Map plan action_type strings → tool handlers (explicit registry, no code exec)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from playwright.async_api import Page

from shared.models.test_plan import Action, TestCase, TestPlan

from . import browser_tool, extraction_tool, form_tool, navigation_tool
from .types import ToolResult

# (page, action, *, timeout_ms, smart_resolve) -> ToolResult
ToolHandler = Callable[..., Awaitable[ToolResult]]

TOOL_REGISTRY: dict[str, ToolHandler] = {
    "navigate": navigation_tool.handle_navigate_action,
    "click": navigation_tool.handle_click_action,
    "hover": navigation_tool.handle_hover_action,
    "fill": form_tool.handle_fill_action,
    "select": form_tool.handle_select_action,
    "wait": browser_tool.handle_wait_action,
    "scroll": browser_tool.handle_scroll_action,
    "keyboard": browser_tool.handle_keyboard_action,
    "screenshot": browser_tool.handle_screenshot_action,
    "extract_text": extraction_tool.handle_extract_text_action,
    "extract_attribute": extraction_tool.handle_extract_attribute_action,
}


def register_tool(action_type: str, handler: ToolHandler) -> None:
    """Register or override a tool for an action_type (e.g. plugins)."""
    TOOL_REGISTRY[action_type] = handler


def tool_names_for_test_case(tc: TestCase) -> set[str]:
    names: set[str] = set()
    for a in tc.preconditions + tc.steps:
        names.add(a.action_type)
    return names


def tool_names_for_plan(plan: TestPlan) -> set[str]:
    names: set[str] = set()
    for tc in plan.test_cases:
        names |= tool_names_for_test_case(tc)
    return names


def resolve_handler(action_type: str) -> ToolHandler | None:
    return TOOL_REGISTRY.get(action_type)
