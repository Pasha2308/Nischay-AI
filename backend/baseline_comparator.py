"""Compare current run result.json with the most recent sibling run under runs/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _fingerprint(issue: dict[str, Any]) -> str:
    return "|".join(
        [
            str(issue.get("type", "")),
            str(issue.get("defect", "")),
            str(issue.get("message", ""))[:200],
            str(issue.get("selector", ""))[:120],
        ]
    )


def _load_report(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def find_previous_result_json(runs_dir: Path, current_run_id: str) -> Path | None:
    """Pick latest sibling run with result.json (by mtime), excluding current_run_id."""
    if not runs_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for d in runs_dir.iterdir():
        if not d.is_dir() or d.name == current_run_id:
            continue
        rj = d / "result.json"
        if rj.exists():
            candidates.append((rj.stat().st_mtime, rj))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def compare_runs(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    """Diff issue lists; regression_score_delta = previous_risk - current_risk (positive = improvement)."""
    if not previous:
        return {
            "status": "no_baseline",
            "message": "First run — baseline established",
            "new_issues": list(current.get("issues") or []),
            "resolved_issues": [],
            "unchanged_issues": [],
            "regression_score_delta": 0,
        }

    cur_issues = list(current.get("issues") or [])
    prev_issues = list(previous.get("issues") or [])

    prev_fp = {_fingerprint(i): i for i in prev_issues}
    cur_fp = {_fingerprint(i): i for i in cur_issues}

    new_issues = [i for fp, i in cur_fp.items() if fp not in prev_fp]
    resolved_issues = [i for fp, i in prev_fp.items() if fp not in cur_fp]
    unchanged_issues = [i for fp, i in cur_fp.items() if fp in prev_fp]

    prev_score = int(previous.get("risk_score") or 0)
    cur_score = int(current.get("risk_score") or 0)
    delta = prev_score - cur_score

    return {
        "status": "ok",
        "message": "Compared with previous report",
        "new_issues": new_issues,
        "resolved_issues": resolved_issues,
        "unchanged_issues": unchanged_issues,
        "regression_score_delta": delta,
        "previous_risk_score": prev_score,
        "current_risk_score": cur_score,
    }


def compare_disk_runs(runs_dir: Path, run_id: str) -> dict[str, Any]:
    """Load runs/<run_id>/result.json and diff against the newest other run with result.json."""
    cur_path = runs_dir / run_id / "result.json"
    current = _load_report(cur_path)
    if not current:
        return {
            "success": False,
            "error": "No result.json for this run_id",
            "code": 404,
        }
    prev_path = find_previous_result_json(runs_dir, run_id)
    previous = _load_report(prev_path) if prev_path else None
    return compare_runs(current, previous)
