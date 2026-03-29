"""
Registry of micro QA tasks for the e-commerce agent.

Maps stable string keys to coroutine functions. Tasks are defined in micro_tasks.py
and executed via run_task() for timeout and structured error handling.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from backend.core.micro_tasks import (
    task_add_to_cart,
    task_apply_coupon,
    task_check_navigation_links,
    task_check_page_load,
    task_contact_support,
    task_fill_address_form,
    task_login_user,
    task_open_product_from_search,
    task_place_order_attempt,
    task_search_product,
    task_start_checkout,
)

MicroTaskFn = Callable[..., Awaitable[dict[str, Any]]]

TASK_REGISTRY: dict[str, MicroTaskFn] = {
    "login_user": task_login_user,
    "search_product": task_search_product,
    "open_product_from_search": task_open_product_from_search,
    "add_to_cart": task_add_to_cart,
    "apply_coupon": task_apply_coupon,
    "start_checkout": task_start_checkout,
    "fill_address_form": task_fill_address_form,
    "place_order_attempt": task_place_order_attempt,
    "contact_support": task_contact_support,
    "check_page_load": task_check_page_load,
    "check_navigation_links": task_check_navigation_links,
}

# User-facing bundles (orchestrator / scan_task)
TASK_GROUPS: dict[str, list[str]] = {
    "quick_scan": [
        "search_product",
        "open_product_from_search",
        "add_to_cart",
    ],
    "conversion_scan": [
        "add_to_cart",
        "apply_coupon",
        "start_checkout",
        "fill_address_form",
    ],
    "auth_scan": [
        "login_user",
    ],
    "full_app_scan": [
        "search_product",
        "add_to_cart",
        "apply_coupon",
        "start_checkout",
        "place_order_attempt",
        "contact_support",
    ],
}

SCAN_TASK_ALIASES: dict[str, str] = {
    "full_app": "full_app_scan",
    "full": "full_app_scan",
    "default": "full_app_scan",
}

# Old ecommerce flow ids → micro tasks (expand_selected_flows compatibility)
LEGACY_FLOW_TO_TASKS: dict[str, list[str]] = {
    "auth": ["login_user"],
    "browse": ["search_product", "open_product_from_search"],
    "cart": ["add_to_cart"],
    "checkout": ["start_checkout", "fill_address_form"],
    "support": ["contact_support"],
    "ui": ["check_page_load"],
    "product": ["open_product_from_search"],
    "navigation": ["check_navigation_links"],
    "search": ["search_product"],
    "coupon": ["apply_coupon"],
}


def get_tasks_from_group(task_group: str) -> list[str]:
    """Resolve a single group name to an ordered list of registered micro task names."""
    key = str(task_group or "").strip().lower()
    key = SCAN_TASK_ALIASES.get(key, key)
    if key not in TASK_GROUPS:
        return []
    out: list[str] = []
    for name in TASK_GROUPS[key]:
        if name in TASK_REGISTRY:
            out.append(name)
    return out


def expand_task_selection(tokens: list[str]) -> list[str]:
    """
    Map tokens to ordered micro task names: group names expand via TASK_GROUPS;
    legacy flow ids via LEGACY_FLOW_TO_TASKS; known task ids pass through.
    No duplicates; first occurrence wins.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in tokens or []:
        t = str(raw).strip().lower()
        if not t:
            continue
        t = SCAN_TASK_ALIASES.get(t, t)
        if t in TASK_GROUPS:
            for name in TASK_GROUPS[t]:
                if name in TASK_REGISTRY and name not in seen:
                    seen.add(name)
                    out.append(name)
            continue
        if t in TASK_REGISTRY:
            if t not in seen:
                seen.add(t)
                out.append(t)
            continue
        if t in LEGACY_FLOW_TO_TASKS:
            for name in LEGACY_FLOW_TO_TASKS[t]:
                if name in TASK_REGISTRY and name not in seen:
                    seen.add(name)
                    out.append(name)
    return out
