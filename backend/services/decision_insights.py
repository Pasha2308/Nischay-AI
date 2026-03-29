"""LLM-backed decision fields: top_risks, business_summary, urgency_score (API payload)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from backend.services.llm_client import LLMClient, _is_placeholder_api_key

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a product risk advisor. Consider the scan's stated task when prioritizing risks "
    "and urgency. Output JSON only — no markdown, no prose outside JSON. "
    "Be short and sharp: exec-ready, decision-oriented."
)

_LEVELS = frozenset({"low", "moderate", "high", "severe"})


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


def _ranked_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = ("critical", "high", "medium", "low")

    def rank(iss: dict[str, Any]) -> tuple[int, str]:
        s = str(iss.get("severity") or "medium").lower()
        try:
            i = order.index(s)
        except ValueError:
            i = 2
        return (i, str(iss.get("message") or ""))

    return sorted(issues, key=rank)


def _fallback_payload(structured: dict[str, Any]) -> dict[str, Any]:
    issues = list(structured.get("issues") or [])
    ranked = _ranked_issues(issues)
    top_risks: list[str] = []
    for iss in ranked[:3]:
        msg = str(iss.get("message") or "").strip()
        if not msg:
            continue
        if len(msg) > 140:
            msg = msg[:137] + "..."
        top_risks.append(msg)
    while len(top_risks) < 3:
        top_risks.append("(none)")

    rs = structured.get("risk_score")
    try:
        rsv = float(rs) if rs is not None else 40.0
    except (TypeError, ValueError):
        rsv = 40.0
    urgency = int(max(1, min(10, round(rsv / 10))))

    counts = _severity_counts(structured.get("issues_by_severity"))
    crit, high = counts.get("critical", 0), counts.get("high", 0)
    if crit > 0 or rsv >= 75:
        rev, usr = "severe", "severe"
    elif high > 1 or rsv >= 50:
        rev, usr = "high", "high"
    elif high > 0 or rsv >= 30:
        rev, usr = "moderate", "moderate"
    else:
        rev, usr = "low", "low"

    return {
        "top_risks": top_risks[:3],
        "business_summary": {
            "revenue_risk_level": rev,
            "user_impact_level": usr,
        },
        "urgency_score": urgency,
    }


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    t = (raw or "").strip()
    if not t:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}\s*$", t)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_payload(data: dict[str, Any], structured: dict[str, Any] | None = None) -> dict[str, Any]:
    fb = _fallback_payload(structured if structured is not None else {})
    tr = data.get("top_risks")
    if not isinstance(tr, list):
        tr = []
    out_risks: list[str] = []
    for x in tr[:3]:
        s = str(x).strip()
        if len(s) > 160:
            s = s[:157] + "..."
        out_risks.append(s if s else "(none)")
    while len(out_risks) < 3:
        out_risks.append("(none)")

    bs = data.get("business_summary")
    rev = usr = "moderate"
    if isinstance(bs, dict):
        r = str(bs.get("revenue_risk_level") or "").strip().lower()
        u = str(bs.get("user_impact_level") or "").strip().lower()
        if r in _LEVELS:
            rev = r
        if u in _LEVELS:
            usr = u

    us = data.get("urgency_score")
    try:
        u_i = int(us)
        u_i = max(1, min(10, u_i))
    except (TypeError, ValueError):
        u_i = int(fb["urgency_score"])

    return {
        "top_risks": out_risks[:3],
        "business_summary": {
            "revenue_risk_level": rev,
            "user_impact_level": usr,
        },
        "urgency_score": u_i,
    }


async def generate_decision_insights(structured: dict[str, Any]) -> dict[str, Any]:
    """top_risks (3), business_summary levels, urgency 1–10."""
    if not isinstance(structured, dict):
        return _fallback_payload({})

    if not _llm_ready():
        return _fallback_payload(structured)

    scan_task = structured.get("scan_task") or "full_app"
    slim = {
        "risk_score": structured.get("risk_score"),
        "risk_level": structured.get("risk_level"),
        "summary": structured.get("summary"),
        "issues_by_severity": structured.get("issues_by_severity"),
        "issues": (structured.get("issues") or [])[:12],
        "scan_mode": structured.get("scan_mode"),
        "scan_task": scan_task,
    }
    raw_json = json.dumps(slim, ensure_ascii=False, default=str, indent=2)
    if len(raw_json) > 45_000:
        raw_json = raw_json[:45_000] + "\n... [truncated]"

    user = (
        f"The scan task was: {scan_task}\n\n"
        "Given this scan result, rate urgency and summarize top business risks "
        "(aligned with that task where relevant).\n\n"
        f"Scan data:\n{raw_json}\n\n"
        "Return JSON ONLY with exactly this shape (no other keys):\n"
        "{\n"
        '  "top_risks": ["<one sharp line>", "<one sharp line>", "<one sharp line>"],\n'
        '  "business_summary": {\n'
        '    "revenue_risk_level": "low" | "moderate" | "high" | "severe",\n'
        '    "user_impact_level": "low" | "moderate" | "high" | "severe"\n'
        "  },\n"
        '  "urgency_score": <integer 1-10>\n'
        "}\n\n"
        'Rules: top_risks must have exactly 3 strings (use \"(none)\" if fewer issues). '
        "Each string max 140 chars. urgency_score 10 = drop-everything; 1 = monitor."
    )

    try:
        llm = LLMClient()
        raw = await llm.complete(_SYSTEM, user)
        parsed = _parse_json_object(raw or "")
        if parsed:
            return _normalize_payload(parsed, structured)
    except Exception as e:
        logger.debug("decision_insights LLM failed: %s", e)

    return _fallback_payload(structured)


async def attach_decision_insights(structured: dict[str, Any]) -> None:
    """Set top_risks, business_summary, urgency_score on structured result in place."""
    payload = await generate_decision_insights(structured)
    structured["top_risks"] = payload["top_risks"]
    structured["business_summary"] = payload["business_summary"]
    structured["urgency_score"] = payload["urgency_score"]
