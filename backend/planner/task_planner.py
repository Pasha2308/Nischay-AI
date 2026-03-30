"""Rule-based task → TestPlan mapping (deterministic, no AI, no code execution)."""

from __future__ import annotations

import time
import uuid
from typing import Callable

from shared.models.config import FrameworkConfig
from shared.models.test_plan import Action, Assertion, TestCase, TestPlan
from shared.utils.url_utils import page_id_from_url

# --- Selectors (aligned with deterministic_plan patterns) ---

_LOGIN_EMAIL = "input[type='email']:visible, input[name*='email' i]:visible, input[name*='user' i]:visible"
_LOGIN_PASSWORD = "input[type='password']:visible, input[name*='pass' i]:visible"
_LOGIN_SUBMIT = (
    "button[type='submit']:visible, input[type='submit']:visible, "
    "button:has-text('Log in'):visible, button:has-text('Login'):visible, "
    "button:has-text('Sign in'):visible"
)

_SEARCH_INPUT = (
    "input[type='search']:visible, input[name*='search' i]:visible, "
    "input[placeholder*='Search' i]:visible, input[aria-label*='search' i]:visible"
)
_SEARCH_SUBMIT = (
    "button[type='submit']:visible, button:has-text('Search'):visible, "
    "[data-testid*='search']:visible, [aria-label*='search' i]:visible"
)

_PRODUCT_LINK = (
    "a[href*='product']:visible, .product a:visible, [data-testid*='product']:visible, "
    "article a:visible, .product-card a:visible"
)
_ADD_TO_CART = (
    "button:has-text('Add to cart'):visible, button:has-text('Add to Cart'):visible, "
    "[data-testid*='add-to-cart']:visible, button[name*='add']:visible, "
    "input[value*='Add']:visible"
)

_LOGGED_IN_HINT = (
    "a[href*='logout']:visible, a[href*='signout']:visible, [href*='sign-out']:visible, "
    "button:has-text('Log out'):visible, [data-testid='account']:visible, "
    "[data-testid='user-menu']:visible"
)

_CART_HINT = "[href*='cart']:visible, [data-testid*='cart']:visible, a[href*='basket']:visible"


def _faker_credentials() -> tuple[str, str]:
    try:
        from faker import Faker

        fake = Faker()
        return fake.email(), fake.password(length=14, special_chars=True, digits=True, upper_case=True)
    except Exception:
        return "task.user@example.com", "TaskTest#2026"


TaskSegment = tuple[list[Action], list[Assertion]]


def _segment_login(config: FrameworkConfig) -> TaskSegment:
    target = (config.target_url or "").strip()
    email, password = _faker_credentials()
    steps = [
        Action(action_type="navigate", value=target, description="Task login: open target URL"),
        Action(action_type="wait", value="800", description="Settle after navigation"),
        Action(action_type="fill", selector=_LOGIN_EMAIL, value=email, description="Task login: fill email (generated)"),
        Action(action_type="fill", selector=_LOGIN_PASSWORD, value=password, description="Task login: fill password (generated)"),
        Action(action_type="click", selector=_LOGIN_SUBMIT, description="Task login: submit form"),
        Action(action_type="wait", value="1500", description="Task login: wait for redirect"),
    ]
    assertions = [
        Assertion(
            assertion_type="element_visible",
            selector=_LOGGED_IN_HINT,
            description="Login success: logout/account UI or URL change implied",
        ),
    ]
    return steps, assertions


def _segment_search_product(_config: FrameworkConfig) -> TaskSegment:
    steps = [
        Action(action_type="wait", value="400", description="Task search: brief settle"),
        Action(
            action_type="fill",
            selector=_SEARCH_INPUT,
            value="shirt",
            description="Task search: enter query",
        ),
        Action(
            action_type="keyboard",
            value="Enter",
            description="Task search: submit search (Enter)",
        ),
        Action(action_type="wait", value="1200", description="Task search: wait for results"),
    ]
    assertions = [
        Assertion(
            assertion_type="page_loaded",
            description="Search: page still loaded after search",
        ),
    ]
    return steps, assertions


def _segment_add_to_cart(_config: FrameworkConfig) -> TaskSegment:
    steps = [
        Action(action_type="wait", value="400", description="Task cart: brief settle"),
        Action(
            action_type="click",
            selector=_PRODUCT_LINK,
            description="Task cart: open first product",
        ),
        Action(action_type="wait", value="900", description="Task cart: product page load"),
        Action(
            action_type="click",
            selector=_ADD_TO_CART,
            description="Task cart: add to cart",
        ),
        Action(action_type="wait", value="800", description="Task cart: wait for cart update"),
    ]
    assertions = [
        Assertion(
            assertion_type="text_contains",
            expected_value="cart",
            description="Cart updated: page body mentions cart",
        ),
        Assertion(
            assertion_type="element_visible",
            selector=_CART_HINT,
            description="Cart updated: cart/basket link or cart test id visible",
        ),
    ]
    return steps, assertions


# Canonical task ids only (after normalization).
_TASK_BUILDERS: dict[str, Callable[[FrameworkConfig], TaskSegment]] = {
    "login": _segment_login,
    "search_product": _segment_search_product,
    "add_to_cart": _segment_add_to_cart,
}

# User-facing aliases → canonical id
_TASK_ALIASES: dict[str, str] = {
    "search": "search_product",
    "addtocart": "add_to_cart",
    "cart": "add_to_cart",
}


def normalize_task_token(raw: str) -> str:
    t = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return _TASK_ALIASES.get(t, t)


def normalize_tasks(task_list: list[str]) -> list[str]:
    out: list[str] = []
    for raw in task_list:
        if not raw or not str(raw).strip():
            continue
        nid = normalize_task_token(str(raw))
        if nid not in _TASK_BUILDERS:
            raise ValueError(f"Unknown task: {raw!r}. Known: {sorted(_TASK_BUILDERS.keys())}")
        out.append(nid)
    return out


def list_known_tasks() -> list[str]:
    return sorted(_TASK_BUILDERS.keys())


def task_catalog() -> dict[str, list[str] | dict[str, str]]:
    """Stable metadata for GET /tasks."""
    return {
        "tasks": list_known_tasks(),
        "aliases": dict(_TASK_ALIASES),
    }


def build_task_test_plan(config: FrameworkConfig, tasks: list[str]) -> TestPlan:
    """Build a single TestCase with sequential steps for all tasks (one browser session)."""
    normalized = normalize_tasks(tasks)
    if not normalized:
        raise ValueError("At least one task is required")

    target = (config.target_url or "").strip()
    if not target:
        raise ValueError("target_url is required")

    page_id = page_id_from_url(target)
    plan_id = f"plan_tasks_{uuid.uuid4().hex[:8]}"
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    merged_steps: list[Action] = []
    merged_assertions: list[Assertion] = []

    for i, tid in enumerate(normalized):
        seg_steps, seg_assertions = _TASK_BUILDERS[tid](config)
        merged_steps.extend(seg_steps)
        merged_assertions.extend(seg_assertions)
        if i < len(normalized) - 1:
            merged_steps.append(
                Action(action_type="wait", value="600", description=f"Between tasks ({tid} → next)"),
            )

    tc = TestCase(
        test_id="task_flow_combined",
        name=f"Task flow ({', '.join(normalized)})",
        description="Rule-based combined task test (deterministic selectors).",
        category="functional",
        priority=1,
        target_page_id=page_id,
        coverage_signature=f"task_flow_{'_'.join(normalized)}_v1",
        requires_auth=False,
        preconditions=[],
        steps=merged_steps,
        assertions=merged_assertions,
        timeout_seconds=max(120, config.selector_timeout_seconds * 5),
    )

    return TestPlan(
        plan_id=plan_id,
        generated_at=generated_at,
        target_url=target,
        test_cases=[tc],
        estimated_duration_seconds=90 * len(normalized),
        coverage_intent={
            "mode": "task_based",
            "tasks": normalized,
            "no_ai": True,
        },
    )
