"""Task-based test execution — builds a TestPlan and reuses the standard Executor."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from backend.planner.task_planner import build_task_test_plan
from backend.structured_run_output import build_structured_output

if TYPE_CHECKING:
    from backend.orchestrator import Orchestrator


async def run_task_pipeline(orch: Orchestrator, tasks: list[str]) -> dict[str, Any]:
    """Execute normalized task ids in one combined TestCase (single browser context)."""
    plan = build_task_test_plan(orch.config, tasks)
    orch._save_plan(plan)
    run_result = await orch._execute(plan)
    duration = round(time.time() - orch._started_at, 2)
    extra: dict[str, Any] = {
        "run_id": run_result.run_id if run_result else None,
        "duration": duration,
        "mode": "task_based",
        "tasks": list(plan.coverage_intent.get("tasks") or tasks),
        "plan_id": plan.plan_id,
    }
    if run_result:
        extra["results"] = {
            "total": run_result.total_tests,
            "passed": run_result.passed,
            "failed": run_result.failed,
            "skipped": run_result.skipped,
            "errors": run_result.errors,
        }
    return build_structured_output(
        site_model=None,
        run_result=run_result,
        pipeline_error=None,
        extra=extra,
    )
