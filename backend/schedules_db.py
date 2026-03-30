from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Schedule

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_listener_added = False


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _run_schedule(schedule_id: str, url: str, flows: list[str] | None) -> None:
    """
    Fire-and-forget scheduled run. Uses Orchestrator pipeline like API runs, but is decoupled from HTTP.
    """
    from shared.models.config import FrameworkConfig
    from backend.orchestrator import Orchestrator
    import api.run_store as run_store
    from backend.db.session import get_async_session_maker
    from backend.db.persistence import persist_pipeline_result

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    job_id = f"sched_{schedule_id}"
    target = (url or "").strip()
    await run_store.create_run(run_id, job_id, target)

    async def emit_bridge(kind: str, name: str, payload: dict[str, Any] | None = None) -> None:
        msg = str((payload or {}).get("message") or "")
        await run_store.append_orchestrator_log(run_id, f"[schedule] {kind}:{name} {msg}".strip())

    cfg = FrameworkConfig(
        target_url=target,
        scan_mode="fast",
        scan_task="full_app_scan",
        flows=list(flows or []) or None,
        crawl_before_execution=False,
    )
    orch = Orchestrator(cfg, emit=emit_bridge, job_id=job_id)
    result: dict[str, Any] | None = None
    success = False
    try:
        result = await asyncio.wait_for(orch._run_pipeline(), timeout=600.0)
        success = bool(result) and not bool((result or {}).get("pipeline_error"))
    except Exception as e:
        logger.exception("schedule run failed id=%s url=%s: %s", schedule_id, target, e)
        success = False

    maker = get_async_session_maker()
    if maker is not None:
        async with maker() as session:
            try:
                await session.execute(
                    update(Schedule)
                    .where(Schedule.id == schedule_id)
                    .values(last_run_at=_utcnow())
                )
                await session.commit()
            except Exception:
                await session.rollback()

    # Persist scan snapshot if available (same as API runs).
    try:
        if result:
            await persist_pipeline_result(target, result, orch._last_site_model, orch._last_run_result)
    except Exception:
        pass


async def sync_schedules_from_db(session: AsyncSession) -> None:
    """
    Load all schedules from DB and register active ones in APScheduler.
    Also updates next_run_at in DB based on computed next run time.
    """
    sched = get_scheduler()
    try:
        sched.remove_all_jobs()
    except Exception:
        pass

    rows = (await session.execute(select(Schedule))).scalars().all()
    for s in rows:
        if not bool(s.is_active):
            continue
        try:
            trig = CronTrigger.from_crontab(s.cron_expression, timezone=s.timezone or "UTC")
        except Exception as e:
            logger.warning("invalid cron for schedule %s: %s", s.id, e)
            continue
        sched.add_job(
            _run_schedule,
            trig,
            args=[s.id, s.url, s.flows],
            id=s.id,
            replace_existing=True,
            misfire_grace_time=120,
        )

    # Update next_run_at from APScheduler computed times.
    try:
        for job in sched.get_jobs():
            nrt = getattr(job, "next_run_time", None)
            if nrt is None:
                continue
            await session.execute(
                update(Schedule).where(Schedule.id == str(job.id)).values(next_run_at=nrt)
            )
        await session.commit()
    except Exception:
        await session.rollback()


async def start_db_scheduler(session: AsyncSession) -> None:
    global _listener_added
    from apscheduler.events import EVENT_JOB_ERROR

    sched = get_scheduler()
    if not _listener_added:
        try:
            sched.add_listener(lambda e: logger.error("scheduler job error: %s", e.exception), EVENT_JOB_ERROR)
        except Exception:
            pass
        _listener_added = True
    await sync_schedules_from_db(session)
    if not sched.running:
        sched.start()


async def stop_db_scheduler() -> None:
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)

