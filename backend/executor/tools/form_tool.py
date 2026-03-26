"""Form tools: fill, select options."""

from __future__ import annotations

import logging
import random
import time

from playwright.async_api import Page
from pydantic import BaseModel, Field

from shared.models.test_plan import Action
from shared.utils.browser_stealth import human_delay

from .resolve import effective_selector
from .types import ToolResult

logger = logging.getLogger(__name__)

_SYNTHETIC_TOKEN = "{{synthetic}}"


def _try_faker():
    try:
        from faker import Faker  # type: ignore

        return Faker()
    except Exception:
        return None


_FAKER = _try_faker()


def _infer_field_kind(action: Action) -> str:
    text = f"{action.selector or ''} {action.description or ''}".lower()
    if "email" in text:
        return "email"
    if "phone" in text or "tel" in text or "mobile" in text:
        return "phone"
    if "name" in text:
        return "name"
    return "name"


def _generate_synthetic_value(kind: str) -> tuple[str, str, str]:
    """Return (value, input_type, case). input_type is valid|invalid."""
    invalid_cases = ["empty", "invalid_email", "long"]

    # Randomly choose valid vs invalid (roughly 70/30)
    is_valid = random.random() < 0.7
    if is_valid:
        if _FAKER:
            if kind == "email":
                return _FAKER.email(), "valid", "valid"
            if kind == "phone":
                return _FAKER.phone_number(), "valid", "valid"
            return _FAKER.name(), "valid", "valid"

        # Fallbacks if faker isn't available at runtime
        if kind == "email":
            return "test.user@example.com", "valid", "valid"
        if kind == "phone":
            return "+1-555-0100", "valid", "valid"
        return "Test User", "valid", "valid"

    case = random.choice(invalid_cases)
    if case == "empty":
        return "", "invalid", case
    if case == "invalid_email":
        return "not-an-email", "invalid", case
    return "x" * 2048, "invalid", case


class FillInput(BaseModel):
    selector: str = Field(..., min_length=1)
    value: str = ""


class SelectInput(BaseModel):
    selector: str = Field(..., min_length=1)
    value: str = ""


def fill_input_from_action(action: Action) -> FillInput:
    if not action.selector:
        raise ValueError("fill requires selector")
    return FillInput(selector=action.selector, value=action.value or "")


async def run_fill(
    page: Page,
    inp: FillInput,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    await human_delay(page, min_ms=80, max_ms=300)
    effective = await effective_selector(
        page, inp.selector, timeout_ms, "fill", smart_resolve=smart_resolve
    )
    logger.debug("Filling %s", effective)
    await page.fill(effective, inp.value, timeout=timeout_ms)
    return ToolResult(
        ok=True,
        action_type="fill",
        message="Field filled",
        data={"selector": effective, "value_length": len(inp.value)},
    )


def select_input_from_action(action: Action) -> SelectInput:
    if not action.selector:
        raise ValueError("select requires selector")
    return SelectInput(selector=action.selector, value=action.value or "")


async def run_select(
    page: Page,
    inp: SelectInput,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    await human_delay(page, min_ms=50, max_ms=250)
    effective = await effective_selector(
        page, inp.selector, timeout_ms, "select", smart_resolve=smart_resolve
    )
    logger.debug("Selecting in %s", effective)
    await page.select_option(effective, inp.value, timeout=timeout_ms)
    return ToolResult(
        ok=True,
        action_type="select",
        message="Option selected",
        data={"selector": effective, "value": inp.value},
    )


async def handle_fill_action(
    page: Page,
    action: Action,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    input_type: str | None = None
    case: str | None = None

    # Synthetic mode: if value is empty or explicit token, generate realistic data.
    if (action.value is None) or (action.value.strip() == "") or (action.value.strip() == _SYNTHETIC_TOKEN):
        # Seed per call so runs vary; still deterministic within the call.
        random.seed(f"{time.time_ns()}::{action.selector}::{action.description}")
        kind = _infer_field_kind(action)
        generated, input_type, case = _generate_synthetic_value(kind)
        action.value = generated  # ensures StepResult captures actual input used

    inp = fill_input_from_action(action)
    res = await run_fill(page, inp, timeout_ms=timeout_ms, smart_resolve=smart_resolve)
    if input_type:
        res.data = {**res.data, "input_type": input_type, "case": case}
    return res


async def handle_select_action(
    page: Page,
    action: Action,
    *,
    timeout_ms: int,
    smart_resolve: bool,
) -> ToolResult:
    inp = select_input_from_action(action)
    return await run_select(page, inp, timeout_ms=timeout_ms, smart_resolve=smart_resolve)
