"""Parse optional user task intent into execution context (no external APIs)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

EmitFn = Callable[[str], Awaitable[None]]


def extract_search_query_from_task_input(text: str) -> str | None:
    """
    If ``text`` signals a product search, return the search keyword(s).

    Examples:
        "search for shoes" -> "shoes"
        "please search dress" -> "dress"
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if not re.search(r"(?i)\bsearch\b", raw):
        return None
    m = re.search(r"(?i)\bsearch\s+for\s+(.+?)(?:[.!?,;]|$)", raw)
    if m:
        q = m.group(1).strip().strip("'\"")
        return q or None
    m = re.search(r"(?i)\bsearch\s+(\S+)", raw)
    if m:
        w = m.group(1).strip()
        if w.lower() not in ("for", "the", "a", "an"):
            return w
    return None


async def apply_task_intent_to_credentials(
    credentials: dict[str, Any],
    task_input: str | None,
    emit: EmitFn,
) -> None:
    """
    Merge parsed intent into ``credentials`` (shared micro-task context).

    Search keywords set ``search_query`` when extractable; otherwise micro-tasks
    keep synthetic / default fallbacks.
    """
    ti = (task_input or "").strip()
    if not ti:
        return
    sq = extract_search_query_from_task_input(ti)
    if sq:
        credentials["search_query"] = sq
        await emit(f"Using user intent: {sq}")
