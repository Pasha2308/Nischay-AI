"""
Run ordered micro tasks for a scan (replaces monolithic ecommerce flows in the orchestrator).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from playwright.async_api import Page

from backend.core.context import create_context, ensure_shared_context
from backend.core.ecommerce_plan import make_safe_emitter
from backend.core.micro_tasks import run_task
from backend.core.task_registry import TASK_REGISTRY, expand_task_selection

logger = logging.getLogger(__name__)

DEFAULT_BUDGET_SECONDS = 90.0
DEFAULT_PER_TASK_CAP = 20.0


async def run_micro_task_group_scan(
    page: Page,
    task_tokens: list[str] | str,
    credentials: dict[str, Any],
    emit_event: Any = None,
    *,
    budget_seconds: float = DEFAULT_BUDGET_SECONDS,
) -> dict[str, Any]:
    """
    Expand group / task tokens, run each micro task with run_task, aggregate defects and results.
    Wall clock capped at budget_seconds (default 90); each task gets min(20s, remaining time).
    """
    emit = make_safe_emitter(emit_event)
    tokens = [task_tokens] if isinstance(task_tokens, str) else list(task_tokens or [])
    selected_tasks = expand_task_selection(tokens)

    if not selected_tasks:
        await emit("⚠ No micro tasks resolved — check scan_task / flows / TASK_GROUPS")
        return {
            "defects": [
                {
                    "defect": "no_micro_tasks",
                    "type": "orchestration",
                    "severity": "high",
                    "page_url": getattr(page, "url", "") or "",
                    "description": "Task selection produced an empty list",
                }
            ],
            "actions": [],
            "metrics": {},
            "task_results": [],
        }

    ctx = create_context()
    if credentials:
        ctx.update(credentials)
    ctx = ensure_shared_context(ctx)

    all_defects: list[dict[str, Any]] = []
    all_actions: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    task_results: list[dict[str, Any]] = []

    deadline = time.monotonic() + float(budget_seconds)

    async def _run_all() -> None:
        nonlocal all_defects, all_actions, metrics, task_results
        for task_name in selected_tasks:
            remaining = deadline - time.monotonic()
            if remaining < 0.5:
                await emit(f"⏱ Scan budget ({budget_seconds}s) exhausted — stopping before {task_name}")
                all_defects.append(
                    {
                        "defect": "scan_budget_exhausted",
                        "type": "orchestration",
                        "severity": "medium",
                        "page_url": getattr(page, "url", "") or "",
                        "description": f"Stopped before {task_name}",
                    }
                )
                break

            task_fn = TASK_REGISTRY.get(task_name)
            if not task_fn:
                await emit(f"⚠ Skipping unknown task: {task_name}")
                continue

            per_timeout = min(DEFAULT_PER_TASK_CAP, max(2.0, remaining - 0.2))
            await emit(f"━━━ Micro task: {task_name} ━━━")
            try:
                result = await run_task(task_fn, page, ctx, emit, timeout=per_timeout)
            except Exception as e:
                logger.exception("micro task %s", task_name)
                await emit(f"❌ {task_name} runner error: {str(e)[:200]}")
                result = {
                    "task": task_name,
                    "success": False,
                    "defects": [{"defect": "task_exception", "description": str(e)[:400], "severity": "high", "page_url": getattr(page, "url", "") or ""}],
                    "impact": "HIGH",
                }

            task_results.append(dict(result))
            metrics[task_name] = {
                "success": result.get("success"),
                "impact": result.get("impact"),
                "defects_count": len(result.get("defects") or []),
            }
            all_actions.append(
                {
                    "task": task_name,
                    "success": result.get("success"),
                    "impact": result.get("impact"),
                }
            )
            for d in result.get("defects") or []:
                if isinstance(d, dict):
                    dd = dict(d)
                    dd.setdefault("micro_task", task_name)
                    all_defects.append(dd)
                else:
                    all_defects.append({"description": str(d), "micro_task": task_name, "severity": "medium"})

            n = len(result.get("defects") or [])
            await emit(f"✅ {task_name} complete — {n} issue(s)")

    try:
        await asyncio.wait_for(_run_all(), timeout=max(0.1, float(budget_seconds)))
    except asyncio.TimeoutError:
        await emit(f"⏱ Global scan cap ({budget_seconds}s) reached")
        all_defects.append(
            {
                "defect": "scan_global_timeout",
                "type": "orchestration",
                "severity": "high",
                "page_url": getattr(page, "url", "") or "",
                "description": f"asyncio guard fired at {budget_seconds}s",
            }
        )

    return {
        "defects": all_defects,
        "actions": all_actions,
        "metrics": metrics,
        "task_results": task_results,
    }
