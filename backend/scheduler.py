"""APScheduler-based recurring QA runs; schedules stored in .qa-framework/schedules.json."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEDULES_DIR = Path(".qa-framework")
SCHEDULES_PATH = SCHEDULES_DIR / "schedules.json"

_scheduler: Any = None
_scheduler_listener_added = False


def _ensure_dir() -> None:
    SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)


def load_schedules() -> list[dict[str, Any]]:
    """Return persisted schedule rows (newest last)."""
    _ensure_dir()
    if not SCHEDULES_PATH.exists():
        return []
    try:
        with open(SCHEDULES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_schedules(rows: list[dict[str, Any]]) -> None:
    _ensure_dir()
    path = SCHEDULES_PATH
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)
    tmp.replace(path)


def get_scheduler() -> Any:
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        _scheduler = AsyncIOScheduler()
    return _scheduler


async def _run_scheduled_pipeline(url: str) -> None:
    """Run full orchestrator pipeline and persist like an HTTP-triggered run."""
    from shared.models.config import FrameworkConfig

    from backend.orchestrator import Orchestrator

    # Local import avoids circular import with api.server at module load.
    import api.run_store as run_store

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    job_id = f"sched_{uuid.uuid4().hex[:10]}"
    u = url.strip()
    await run_store.create_run(run_id, job_id, u)

    class _Hooks:
        async def on_pipeline_started(self) -> None:
            await run_store.append_orchestrator_log(run_id, "[scheduler] pipeline started")

        async def on_pipeline_finished(self, *, success: bool, result: dict[str, Any]) -> None:
            pe = result.get("pipeline_error")
            line = f"[scheduler] pipeline finished success={success}"
            if pe:
                line += f" pipeline_error={pe!r}"
            await run_store.append_orchestrator_log(run_id, line)

    try:
        orch = Orchestrator(
            FrameworkConfig(target_url=u),
            run_id=run_id,
            on_run_event=None,
            run_hooks=_Hooks(),
        )
        result = await asyncio.wait_for(orch._run_pipeline(), timeout=600.0)
    except Exception as e:
        logger.exception("Scheduled run failed for %s: %s", u, e)
        await run_store.finalize_run(
            run_id,
            status="failed",
            result=None,
            error=str(e),
            partial=False,
        )
        return

    partial = bool((result or {}).get("partial"))
    pe = (result or {}).get("pipeline_error")
    if pe:
        await run_store.finalize_run(
            run_id,
            status="failed",
            result=result if isinstance(result, dict) else None,
            error=str(pe),
            partial=False,
        )
    elif partial:
        await run_store.finalize_run(
            run_id,
            status="success",
            result=result if isinstance(result, dict) else None,
            error=None,
            partial=True,
        )
    else:
        await run_store.finalize_run(
            run_id,
            status="success",
            result=result if isinstance(result, dict) else None,
            error=None,
            partial=False,
        )
    logger.info("Scheduled run finished run_id=%s url=%s", run_id, u)


def _job_listener(event: Any) -> None:
    if event.exception:
        logger.error("Scheduler job exception: %s", event.exception)


def reschedule_all_jobs() -> None:
    """Reload jobs from disk (call after add/remove)."""
    from apscheduler.triggers.cron import CronTrigger

    sched = get_scheduler()
    try:
        sched.remove_all_jobs()
    except Exception:
        pass

    for row in load_schedules():
        sid = row.get("schedule_id")
        url = row.get("url")
        cron = row.get("cron")
        if not sid or not url or not cron:
            continue
        try:
            trig = CronTrigger.from_crontab(cron)
        except Exception as e:
            logger.warning("Invalid cron for schedule %s: %s", sid, e)
            continue
        sched.add_job(
            _run_scheduled_pipeline,
            trig,
            args=[url],
            id=sid,
            replace_existing=True,
            misfire_grace_time=120,
        )


async def start_scheduler() -> None:
    global _scheduler_listener_added
    from apscheduler.events import EVENT_JOB_ERROR

    sched = get_scheduler()
    if not _scheduler_listener_added:
        try:
            sched.add_listener(_job_listener, EVENT_JOB_ERROR)
            _scheduler_listener_added = True
        except Exception:
            pass
    reschedule_all_jobs()
    if not sched.running:
        sched.start()


async def stop_scheduler() -> None:
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)


def add_schedule(url: str, cron: str) -> dict[str, Any]:
    """Append schedule and register job."""
    rows = load_schedules()
    sid = f"sch_{uuid.uuid4().hex[:12]}"
    row = {
        "schedule_id": sid,
        "url": url.strip(),
        "cron": cron.strip(),
    }
    rows.append(row)
    save_schedules(rows)
    reschedule_all_jobs()
    return row


def remove_schedule(schedule_id: str) -> bool:
    rows = load_schedules()
    new_rows = [r for r in rows if r.get("schedule_id") != schedule_id]
    if len(new_rows) == len(rows):
        return False
    save_schedules(new_rows)
    reschedule_all_jobs()
    return True
