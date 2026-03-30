"""Persist per-run artifacts under runs/<run_id>/: execution trace, console logs, metadata."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from shared.models.test_result import StepResult, TestResult


def write_console_logs_txt(run_dir: Path, lines: list[str]) -> Path:
    """Write aggregated console lines to runs/<run_id>/console_logs.txt."""
    path = run_dir / "console_logs.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_execution_trace_json(
    run_dir: Path,
    pre: list[StepResult],
    steps: list[StepResult],
) -> Path:
    """Structured trace derived from step results (action, status, error, screenshot_path)."""
    trace: list[dict[str, Any]] = []
    for sr in pre:
        trace.append(
            {
                "phase": "precondition",
                "step_index": sr.step_index,
                "action": {
                    "action_type": sr.action_type,
                    "selector": sr.selector,
                    "value": sr.value,
                    "description": sr.description,
                },
                "status": sr.status,
                "error": sr.error_message,
                "screenshot_path": sr.screenshot_path,
                "duration_ms": None,
            }
        )
    for sr in steps:
        trace.append(
            {
                "phase": "step",
                "step_index": sr.step_index,
                "action": {
                    "action_type": sr.action_type,
                    "selector": sr.selector,
                    "value": sr.value,
                    "description": sr.description,
                },
                "status": sr.status,
                "error": sr.error_message,
                "screenshot_path": sr.screenshot_path,
                "duration_ms": None,
            }
        )
    path = run_dir / "execution_trace.json"
    path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    return path


def write_metadata_json(
    run_dir: Path,
    *,
    run_id: str,
    url: str,
    status: str,
    started_at: float | str | None,
    completed_at: float | str | None,
    duration_seconds: float | None,
    risk_score: int | None,
    risk_level: str | None,
) -> Path:
    """metadata.json for the run directory."""
    meta = {
        "run_id": run_id,
        "url": url,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration_seconds,
        "risk_score": risk_score,
        "risk_level": risk_level,
    }
    path = run_dir / "metadata.json"
    path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return path


def write_execution_trace_from_test_results(run_dir: Path, test_results: list[TestResult]) -> Path:
    """Flatten precondition + step results from all tests into execution_trace.json."""
    trace: list[dict[str, Any]] = []
    action_index = 0
    for tr in test_results:
        for phase, srs in (
            ("precondition", tr.precondition_results),
            ("step", tr.step_results),
        ):
            for sr in srs:
                trace.append(
                    {
                        "action_index": action_index,
                        "test_id": tr.test_id,
                        "phase": phase,
                        "step_index": sr.step_index,
                        "action": {
                            "action_type": sr.action_type,
                            "selector": sr.selector,
                            "value": sr.value,
                            "description": sr.description,
                        },
                        "status": sr.status,
                        "error": sr.error_message,
                        "screenshot_path": sr.screenshot_path,
                        "duration_ms": None,
                    }
                )
                action_index += 1
    path = run_dir / "execution_trace.json"
    path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    return path


def copy_screenshots_indexed(run_dir: Path, test_results: list[TestResult]) -> list[str]:
    """Copy per-step screenshots into runs/<run_id>/screenshots/<n>.png for stable paths."""
    out_dir = run_dir / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    idx = 0
    for tr in test_results:
        for sr in list(tr.precondition_results) + list(tr.step_results):
            src = sr.screenshot_path
            if not src:
                idx += 1
                continue
            sp = Path(src)
            if not sp.is_file():
                idx += 1
                continue
            dest = out_dir / f"{idx}.png"
            try:
                shutil.copy2(sp, dest)
                copied.append(str(dest))
            except OSError:
                pass
            idx += 1
    return copied
