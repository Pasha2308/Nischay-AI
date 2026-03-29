"""Short LLM explanation for aggregate risk score (API payload: risk_explanation)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from backend.services.llm_client import LLMClient, _is_placeholder_api_key

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You explain digital product risk scores for executives and PMs. "
    "Output must be plain text only: exactly 2–3 short lines (under 80 words total). "
    "No headings, no bullet labels, no markdown."
)


def _llm_ready() -> bool:
    key = (os.environ.get("LLM_API_KEY") or "").strip()
    if not key or _is_placeholder_api_key(key):
        return False
    if not (os.environ.get("LLM_MODEL") or "").strip():
        return False
    if not (os.environ.get("LLM_BASE_URL") or "").strip():
        return False
    return True


def _severity_counts(issues_by_severity: Any) -> dict[str, int]:
    if not isinstance(issues_by_severity, dict):
        return {}
    out: dict[str, int] = {}
    for k in ("critical", "high", "medium", "low"):
        v = issues_by_severity.get(k)
        out[k] = len(v) if isinstance(v, list) else 0
    return out


def _top_issue_snippets(issues: list[dict[str, Any]], n: int = 3) -> list[str]:
    order = ("critical", "high", "medium", "low")
    def rank(iss: dict[str, Any]) -> tuple[int, str]:
        s = str(iss.get("severity") or "medium").lower()
        try:
            i = order.index(s)
        except ValueError:
            i = 2
        return (i, str(iss.get("message") or "")[:120])
    ranked = sorted(issues, key=rank)
    out: list[str] = []
    for iss in ranked[:n]:
        m = str(iss.get("message") or "").strip()[:200]
        if m:
            out.append(m)
    return out


def _fallback_explanation(structured: dict[str, Any]) -> str:
    rs = structured.get("risk_score")
    level = structured.get("risk_level") or ""
    issues = structured.get("issues") or []
    counts = _severity_counts(structured.get("issues_by_severity"))
    n = len(issues) if isinstance(issues, list) else 0
    crit = counts.get("critical", 0)
    high = counts.get("high", 0)
    return (
        f"The score reflects {n} open issues ({crit} critical, {high} high). "
        f"Severity mix and journey exposure lift the {rs}-point {level} rating. "
        f"Tackle critical and high items first to protect users and revenue."
    )


def _clamp_lines(text: str, max_lines: int = 3) -> str:
    t = (text or "").strip()
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines:
        single = re.sub(r"\s+", " ", t)
        if len(single) > 500:
            return single[:497] + "..."
        return single
    lines = lines[:max_lines]
    out = "\n".join(lines)
    if len(out) > 600:
        return out[:597] + "..."
    return out


async def generate_risk_explanation(structured: dict[str, Any]) -> str:
    """2–3 lines: why the score, main drivers, business meaning."""
    if not isinstance(structured, dict):
        return ""

    rs = structured.get("risk_score")
    level = structured.get("risk_level", "")
    legacy = structured.get("risk_level_legacy", "")
    summary = structured.get("summary") or {}
    counts = _severity_counts(structured.get("issues_by_severity"))
    tops = _top_issue_snippets(list(structured.get("issues") or []), 3)
    delta = structured.get("delta_report")

    if not _llm_ready():
        return _fallback_explanation(structured)

    msg_lines = [
        f"risk_score (0–100): {rs}",
        f"risk_level: {level}" + (f" (legacy label: {legacy})" if legacy else ""),
        f"summary: {json.dumps(summary, default=str)[:1500]}",
        f"issue counts by severity: {json.dumps(counts)}",
        "Representative issue messages:",
    ]
    if tops:
        msg_lines.extend(f"  - {t}" for t in tops)
    else:
        msg_lines.append("  (none)")
    user = "\n".join(msg_lines)
    if isinstance(delta, dict) and delta.get("compared_to_scan_id") is not None:
        user += (
            f"\nscan delta vs last run: risk_change={delta.get('risk_change')!r}, "
            f"trend_direction={delta.get('trend_direction')!r}"
        )
    user += (
        "\n\nExplain in 2–3 short lines total:\n"
        "Why this risk score is where it is (high vs low drivers).\n"
        "Which factors contributed most (severity mix, issue types, churn vs last scan if given).\n"
        "Business meaning (users, revenue, trust) in plain language."
    )

    try:
        llm = LLMClient()
        raw = await llm.complete(_SYSTEM, user)
        text = _clamp_lines(raw or "", max_lines=3)
        return text or _fallback_explanation(structured)
    except Exception as e:
        logger.debug("risk_explanation LLM failed: %s", e)
        return _fallback_explanation(structured)


async def attach_risk_explanation(structured: dict[str, Any]) -> None:
    """Set structured['risk_explanation'] in place."""
    structured["risk_explanation"] = await generate_risk_explanation(structured)
