"""JSON registry + per-run logs under runs/."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from shared.models.run_record import RunRecord, RunStatus

from backend.run_artifacts import write_metadata_json

REGISTRY_FILENAME = "registry.json"
_registry_lock = asyncio.Lock()


def runs_root() -> Path:
    root = Path("runs")
    root.mkdir(parents=True, exist_ok=True)
    return root


def registry_path() -> Path:
    return runs_root() / REGISTRY_FILENAME


def run_dir(run_id: str) -> Path:
    p = runs_root() / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_path(run_id: str) -> Path:
    return run_dir(run_id) / "logs.txt"


def result_path(run_id: str) -> Path:
    return run_dir(run_id) / "result.json"


def _load_registry_sync() -> dict[str, Any]:
    path = registry_path()
    if not path.exists():
        return {"version": 1, "runs": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "runs" not in data:
        data = {"version": 1, "runs": []}
    return data


def _save_registry_sync(runs: list[dict[str, Any]]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "runs": runs}
    fd, tmp = tempfile.mkstemp(prefix="registry_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _append_log_sync(run_id: str, line: str) -> None:
    lp = logs_path(run_id)
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def _risk_and_summary_from_result(result: dict[str, Any] | None) -> tuple[int | None, str | None]:
    if not result:
        return None, None
    risk = result.get("risk_score")
    try:
        risk_i = int(risk) if risk is not None else None
    except (TypeError, ValueError):
        risk_i = None
    summary = result.get("executive_summary")
    if not summary and result.get("summary"):
        s = result["summary"]
        if isinstance(s, dict):
            summary = (
                f"Pages: {s.get('total_pages_scanned', 0)}, "
                f"actions: {s.get('total_actions_run', 0)}, "
                f"issues: {s.get('total_issues_found', 0)}"
            )
    if isinstance(summary, str):
        return risk_i, summary[:2000]
    return risk_i, None


async def create_run(run_id: str, job_id: str, target_url: str) -> RunRecord:
    """Register a new run as running; create logs file with header."""
    record = RunRecord(
        run_id=run_id,
        job_id=job_id,
        target_url=target_url,
        status="running",
        start_time=__import__("time").time(),
    )
    async with _registry_lock:
        data = _load_registry_sync()
        runs_raw = data.get("runs", [])
        # de-dup by run_id
        runs_raw = [r for r in runs_raw if r.get("run_id") != run_id]
        runs_raw.append(record.model_dump())
        _save_registry_sync(runs_raw)
    line = f"[start] run_id={run_id} job_id={job_id} url={target_url}"
    await asyncio.to_thread(_append_log_sync, run_id, line)
    return record


def _write_metadata_for_finalize(
    run_id: str, rec: dict[str, Any], result: dict[str, Any] | None
) -> None:
    """Write runs/<run_id>/metadata.json aligned with registry + optional API result."""
    from datetime import datetime, timezone

    def iso(ts: Any) -> str | None:
        if ts is None:
            return None
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError, OSError):
            return None

    start = rec.get("start_time")
    end = rec.get("end_time")
    dur = None
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        dur = round(float(end) - float(start), 3)
    risk = rec.get("risk_score")
    if result and result.get("risk_score") is not None:
        try:
            risk = int(result.get("risk_score"))
        except (TypeError, ValueError):
            pass
    rl = (result or {}).get("risk_level")
    try:
        rsi = int(risk) if risk is not None else None
    except (TypeError, ValueError):
        rsi = None
    write_metadata_json(
        run_dir(run_id),
        run_id=run_id,
        url=str(rec.get("target_url", "")),
        status=str(rec.get("status", "")),
        started_at=iso(start),
        completed_at=iso(end),
        duration_seconds=dur,
        risk_score=rsi,
        risk_level=str(rl) if rl is not None else None,
    )


async def append_event_log(run_id: str, event_type: str, message: str, timestamp: float) -> None:
    """Append one line for a streamed / job event."""
    from datetime import datetime, timezone

    ts = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] [{event_type}] {message}"
    await asyncio.to_thread(_append_log_sync, run_id, line)


async def finalize_run(
    run_id: str,
    *,
    status: RunStatus,
    result: dict[str, Any] | None,
    error: str | None,
    partial: bool,
) -> RunRecord | None:
    """Set end_time, status, risk, summary; write result.json when provided."""
    async with _registry_lock:
        data = _load_registry_sync()
        runs_raw = data.get("runs", [])
        idx = next((i for i, r in enumerate(runs_raw) if r.get("run_id") == run_id), None)
        if idx is None:
            return None
        if runs_raw[idx].get("end_time") is not None:
            return RunRecord.model_validate(runs_raw[idx])
        end_t = time.time()
        risk, summary = _risk_and_summary_from_result(result)
        rec = dict(runs_raw[idx])
        rec["end_time"] = end_t
        rec["status"] = status
        rec["partial"] = partial
        rec["error"] = error
        if risk is not None:
            rec["risk_score"] = risk
        if summary:
            rec["summary"] = summary
        elif error:
            rec["summary"] = error[:2000]
        runs_raw[idx] = rec
        _save_registry_sync(runs_raw)
        out = RunRecord.model_validate(rec)

    if result is not None:
        rp = result_path(run_id)
        await asyncio.to_thread(_write_json_sync, rp, result)
    # FIXED: mirror registry timing and risk into metadata.json for tooling and UI.
    await asyncio.to_thread(_write_metadata_for_finalize, run_id, rec, result)
    fin_line = f"[end] status={status} partial={partial} error={error!r}"
    await asyncio.to_thread(_append_log_sync, run_id, fin_line)
    return out


def _write_json_sync(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="result_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


async def list_runs() -> list[RunRecord]:
    async with _registry_lock:
        data = _load_registry_sync()
        runs_raw = data.get("runs", [])
    records = [RunRecord.model_validate(r) for r in runs_raw]
    records.sort(key=lambda r: r.start_time, reverse=True)
    return records


async def get_run(run_id: str) -> RunRecord | None:
    async with _registry_lock:
        data = _load_registry_sync()
        for r in data.get("runs", []):
            if r.get("run_id") == run_id:
                return RunRecord.model_validate(r)
    return None


async def get_run_result_json(run_id: str) -> dict[str, Any] | None:
    path = result_path(run_id)
    if not path.exists():
        return None

    def _read() -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    return await asyncio.to_thread(_read)


async def get_run_logs_text(run_id: str) -> str | None:
    path = logs_path(run_id)
    if not path.exists():
        return None

    def _read() -> str:
        with open(path, encoding="utf-8") as f:
            return f.read()

    return await asyncio.to_thread(_read)


async def append_orchestrator_log(run_id: str, line: str) -> None:
    await asyncio.to_thread(_append_log_sync, run_id, line)
