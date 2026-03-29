"""
Shared mutable context for micro QA tasks.

Callers may merge extra keys onto the dict returned by create_context().
Tasks use ensure_shared_context() so standalone runs still get default keys.
"""

from __future__ import annotations

from typing import Any


def create_context() -> dict[str, Any]:
    return {
        "selected_product": None,
        "cart_items": 0,
        "login_state": False,
        "last_errors": [],
    }


def ensure_shared_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """
    Ensure standard keys exist on context (mutates dict in place when provided).
    If context is None, returns a new dict from create_context().
    """
    if context is None:
        return create_context()
    defaults = create_context()
    for key, value in defaults.items():
        if key not in context:
            context[key] = [] if key == "last_errors" else value
    return context
