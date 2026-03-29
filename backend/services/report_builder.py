"""Build CTO-level reports from real scan payloads (defects, flows, actions, timing)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from backend.core.decision_engine import generate_decision
from backend.services.llm_client import LLMClient, _is_placeholder_api_key

logger = logging.getLogger(__name__)

_SEVERITY_WEIGHT: dict[str, int] = {
    "critical": 40,
    "high": 25,
    "medium": 15,
    "low": 5,
}

_SCORECARD_KEYS = ("revenue", "trust", "ux", "data", "support")

_IMPACT_ALIASES: dict[str, str] = {
    "revenue": "revenue",
    "rev": "revenue",
    "trust": "trust",
    "security": "trust",
    "ux": "ux",
    "user experience": "ux",
    "ui": "ux",
    "performance": "ux",
    "data": "data",
    "support": "support",
    "customer support": "support",
}


def _normalize_severity(raw: str | None) -> str:
    s = (raw or "medium").strip().lower()
    if s in ("critical", "crit", "sev1", "blocker"):
        return "critical"
    if s in ("high", "error"):
        return "high"
    if s in ("low", "info", "minor"):
        return "low"
    if s in ("medium", "med", "warn", "warning"):
        return "medium"
    return "medium"


def _infer_impact_bucket(defect: Mapping[str, Any]) -> str:
    explicit = str(defect.get("impact") or "").strip().lower()
    if explicit:
        for k, v in _IMPACT_ALIASES.items():
            if k in explicit:
                return v
        if explicit in _SCORECARD_KEYS:
            return explicit
    page = str(defect.get("page_url") or "").lower()
    dt = f"{defect.get('defect') or defect.get('type') or ''} {defect.get('description') or ''}".lower()
    combined = f"{page} {dt}"
    if any(x in combined for x in ("checkout", "cart", "payment", "order", "pricing", "promo")):
        return "revenue"
    if any(x in combined for x in ("login", "auth", "password", "session", "trust")):
        return "trust"
    if any(
        x in combined
        for x in ("console", "slow", "load", "ui", "form", "navigation", "broken_image", "cta")
    ):
        return "ux"
    if any(x in combined for x in ("total", "tax", "mismatch", "data", "math")):
        return "data"
    if any(x in combined for x in ("support", "chat", "contact", "help", "faq")):
        return "support"
    return "ux"


def _defect_title(d: Mapping[str, Any]) -> str:
    t = str(d.get("title") or "").strip()
    if t:
        return t[:240]
    return str(d.get("defect") or d.get("type") or "issue")[:240]


def _flatten_defects(scan: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    raw = scan.get("defects")
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, dict):
                out.append(dict(x))
    flows = scan.get("flows")
    if isinstance(flows, list):
        for fl in flows:
            if not isinstance(fl, dict):
                continue
            fds = fl.get("defects")
            if isinstance(fds, list):
                for x in fds:
                    if isinstance(x, dict):
                        row = dict(x)
                        row.setdefault("flow", fl.get("name"))
                        out.append(row)
    # dedupe by (page_url, defect, description[:80])
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for d in out:
        key = f"{d.get('page_url')}|{d.get('defect')}|{str(d.get('description',''))[:80]}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)
    return deduped


def _task_results_from_scan(scan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Prefer ``task_results``; otherwise synthesize from per-task ``metrics`` (micro scan)."""
    raw = scan.get("task_results")
    if isinstance(raw, list) and raw:
        return [dict(x) for x in raw if isinstance(x, dict)]
    metrics = scan.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return []
    out: list[dict[str, Any]] = []
    for name, meta in metrics.items():
        if not isinstance(meta, dict):
            continue
        success = bool(meta.get("success", True))
        impact = str(meta.get("impact") or "LOW").strip().upper()
        if impact not in ("LOW", "MEDIUM", "HIGH"):
            impact = "LOW"
        out.append(
            {
                "task": str(name),
                "success": success,
                "impact": impact,
                "defects": [],
            }
        )
    return out


def _flows_from_scan(scan: Mapping[str, Any]) -> list[dict[str, Any]]:
    flows = scan.get("flows")
    if isinstance(flows, list) and flows:
        return [dict(f) if isinstance(f, dict) else {"name": str(f)} for f in flows]
    defects = _flatten_defects(scan)
    if defects or scan.get("action_trail"):
        return [
            {
                "name": "pipeline",
                "defects": defects,
                "metrics": scan.get("metrics") or {},
                "actions": scan.get("action_trail") or [],
            }
        ]
    return [{"name": "pipeline", "defects": [], "metrics": {}, "actions": []}]


def _pages_visited(scan: Mapping[str, Any], defects: Sequence[Mapping[str, Any]]) -> list[str]:
    pages = scan.get("pages_visited")
    if isinstance(pages, list) and pages:
        return sorted({str(p).strip() for p in pages if str(p).strip()})
    urls: set[str] = set()
    for d in defects:
        u = str(d.get("page_url") or "").strip()
        if u:
            urls.add(u)
    trail = scan.get("action_trail")
    if isinstance(trail, list):
        for a in trail:
            if not isinstance(a, dict):
                continue
            u = str(a.get("page_url") or a.get("target_url") or "").strip()
            if u:
                urls.add(u)
    tu = str(scan.get("target_url") or "").strip()
    if tu:
        urls.add(tu)
    return sorted(urls)


def _rule_based_executive_summary(scan: Mapping[str, Any], defects: list[dict[str, Any]]) -> list[str]:
    n = len(defects)
    sev_counts: dict[str, int] = {k: 0 for k in ("critical", "high", "medium", "low")}
    for d in defects:
        sev_counts[_normalize_severity(str(d.get("severity")))] += 1
    flows = _flows_from_scan(scan)
    flow_names = ", ".join(str(f.get("name")) for f in flows if f.get("name")) or "recorded flows"
    dur = scan.get("duration_seconds")
    dur_s = f"{float(dur):.1f}s" if isinstance(dur, (int, float)) else "n/a"
    line1 = (
        f"Scan captured {n} distinct issue(s): "
        f"critical={sev_counts['critical']}, high={sev_counts['high']}, "
        f"medium={sev_counts['medium']}, low={sev_counts['low']}."
    )
    worst = max(defects, key=lambda d: _SEVERITY_WEIGHT.get(_normalize_severity(str(d.get("severity"))), 0), default=None)
    if worst:
        line2 = (
            f"Highest-weight finding: {_normalize_severity(str(worst.get('severity')))} "
            f"— {_defect_title(worst)[:120]} ({_infer_impact_bucket(worst)})."
        )
    else:
        line2 = "Highest-weight finding: none — defect list empty for this payload."
    line3 = f"Flows in scope: {flow_names}; wall time {dur_s}; target {str(scan.get('target_url') or 'n/a')[:120]}."
    return [line1, line2, line3]


def _validate_three_lines(text: str) -> bool:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return len(lines) == 3 and all(len(ln) > 0 for ln in lines)


async def _llm_executive_summary(scan: Mapping[str, Any], defects: list[dict[str, Any]]) -> str | None:
    if not _llm_ready():
        return None
    payload = {
        "target_url": scan.get("target_url"),
        "duration_seconds": scan.get("duration_seconds"),
        "defect_count": len(defects),
        "severity_breakdown": {
            k: sum(1 for d in defects if _normalize_severity(str(d.get("severity"))) == k)
            for k in ("critical", "high", "medium", "low")
        },
        "top_defects": [
            {
                "severity": _normalize_severity(str(d.get("severity"))),
                "type": d.get("defect") or d.get("type"),
                "impact": _infer_impact_bucket(d),
                "page_url": (str(d.get("page_url") or "")[:200]),
            }
            for d in sorted(
                defects,
                key=lambda x: _SEVERITY_WEIGHT.get(_normalize_severity(str(x.get("severity"))), 0),
                reverse=True,
            )[:12]
        ],
    }
    system = (
        "You write executive summaries for engineering leadership. "
        "Use ONLY the JSON facts provided — no placeholders, no advice invented without basis in counts."
    )
    user = (
        "Output EXACTLY 3 lines of plain text.\n"
        "Line 1: factual statement of issue volume and severity mix.\n"
        "Line 2: factual statement of the worst single risk area using the data.\n"
        "Line 3: factual statement tying flows, duration, and target URL.\n"
        "No markdown, no numbering, no extra lines.\n\n"
        "FACTS_JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    client = LLMClient()
    return await client.complete(system, user, fast=True)


async def _llm_fix_suggestion(defect: Mapping[str, Any]) -> str | None:
    if not _llm_ready():
        return None
    system = "You are a principal engineer. Suggest one concrete fix from the defect record only."
    payload = {
        "severity": defect.get("severity"),
        "type": defect.get("defect") or defect.get("type"),
        "page_url": defect.get("page_url"),
        "description": (str(defect.get("description") or "")[:1500]),
    }
    user = (
        "Defect (JSON):\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "Reply with ONE short imperative sentence (max 220 chars), no quotes."
    )
    client = LLMClient()
    return (await client.complete(system, user, fast=True)).strip()


def _llm_ready() -> bool:
    import os

    key = (os.environ.get("LLM_API_KEY") or "").strip()
    return bool(key) and not _is_placeholder_api_key(key)


def _rule_fix_suggestion(defect: Mapping[str, Any]) -> str:
    sev = _normalize_severity(str(defect.get("severity")))
    dt = _defect_title(defect)
    page = str(defect.get("page_url") or "unknown page")[:200]
    desc = str(defect.get("description") or "").strip()
    tail = f" Evidence: {desc[:160]}." if desc else ""
    return f"[{sev}] Resolve «{dt}» on {page}.{tail}"


def _scorecards(defects: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for dim in _SCORECARD_KEYS:
        bucket = [d for d in defects if _infer_impact_bucket(d) == dim]
        raw = sum(_SEVERITY_WEIGHT.get(_normalize_severity(str(d.get("severity"))), 15) for d in bucket)
        score = max(0.0, 100.0 - min(100.0, float(raw)))
        out[dim] = {
            "dimension": dim,
            "score": round(score, 1),
            "weighted_penalty": int(min(100, raw)),
            "defects_in_dimension": len(bucket),
            "severity_breakdown": {
                k: sum(1 for d in bucket if _normalize_severity(str(d.get("severity"))) == k)
                for k in ("critical", "high", "medium", "low")
            },
        }
    return out


def _most_critical(defects: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not defects:
        return None
    order = ("critical", "high", "medium", "low")
    best = max(
        defects,
        key=lambda d: (
            -order.index(_normalize_severity(str(d.get("severity"))))
            if _normalize_severity(str(d.get("severity"))) in order
            else -2,
            _SEVERITY_WEIGHT.get(_normalize_severity(str(d.get("severity"))), 0),
        ),
    )
    return {
        "severity": _normalize_severity(str(best.get("severity"))),
        "title": _defect_title(best),
        "impact": _infer_impact_bucket(best),
    }


def _action_context_for_page(
    trail: Sequence[Mapping[str, Any]], page_url: str
) -> str:
    if not page_url or not trail:
        return ""
    hits = [
        str(a.get("description") or a.get("step") or a.get("action_type") or "")
        for a in trail
        if isinstance(a, dict) and str(a.get("page_url") or "") == page_url
    ]
    if not hits:
        return ""
    return " | ".join(h[:120] for h in hits if h)[:500]


def _screenshot_for_defect(
    defect: Mapping[str, Any], trail: Sequence[Mapping[str, Any]]
) -> str:
    for key in ("screenshot", "screenshot_path", "evidence_path"):
        v = defect.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    page = str(defect.get("page_url") or "")
    for a in trail:
        if not isinstance(a, dict):
            continue
        if str(a.get("page_url") or "") == page and a.get("screenshot_path"):
            return str(a.get("screenshot_path"))
    return ""


def _chronological_trail(scan: Mapping[str, Any]) -> list[dict[str, Any]]:
    trail = scan.get("action_trail")
    if not isinstance(trail, list):
        return []
    rows: list[tuple[float | int, dict[str, Any]]] = []
    for i, a in enumerate(trail):
        if not isinstance(a, dict):
            continue
        t = a.get("timestamp") or a.get("ts") or a.get("time")
        sort_key: float | int = 0
        if isinstance(t, (int, float)):
            sort_key = float(t)
        elif isinstance(t, str):
            try:
                sort_key = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
            except Exception:
                sort_key = i
        else:
            sort_key = i
        rows.append((sort_key, dict(a)))
    rows.sort(key=lambda x: x[0])
    return [r[1] for r in rows]


def _recommendations(defects: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    ranked = sorted(
        defects,
        key=lambda d: (
            -_SEVERITY_WEIGHT.get(_normalize_severity(str(d.get("severity"))), 0),
            str(d.get("page_url") or ""),
        ),
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in ranked:
        title = _defect_title(d)
        if title in seen:
            continue
        seen.add(title)
        out.append(
            {
                "priority": len(out) + 1,
                "severity": _normalize_severity(str(d.get("severity"))),
                "title": title,
                "page": str(d.get("page_url") or ""),
                "impact": _infer_impact_bucket(d),
                "rationale": str(d.get("description") or "")[:400],
            }
        )
        if len(out) >= limit:
            break
    return out


async def build_cto_report(scan_payload: Mapping[str, Any]) -> dict[str, Any]:
    """
    Transform a scan payload into a CTO report dict. All sections are populated from
    ``scan_payload`` keys: ``target_url``, ``duration_seconds``, ``started_at``,
    ``completed_at``, ``flows`` (list of flow dicts with optional ``name``, ``defects``, ``metrics``),
    ``defects`` (flat list), ``action_trail`` (list of dicts), ``pages_visited`` (optional),
    ``task_results`` (per micro-task dicts from the runner) or ``metrics`` (per-task success/impact) for ``shipping_decision``.

    LLM sections require a configured ``LLM_API_KEY``; otherwise rule-based text is used
    (still derived only from supplied data).
    """
    scan = dict(scan_payload)
    defects = _flatten_defects(scan)
    flows = _flows_from_scan(scan)
    trail = _chronological_trail(scan)

    # --- 1 Executive summary
    summary_source = "rules"
    exec_lines = _rule_based_executive_summary(scan, defects)
    if _llm_ready():
        try:
            raw = await _llm_executive_summary(scan, defects)
            if raw and _validate_three_lines(raw):
                exec_lines = [ln.strip() for ln in raw.splitlines() if ln.strip()][:3]
                summary_source = "llm"
            else:
                raw2 = await _llm_executive_summary(scan, defects)
                if raw2 and _validate_three_lines(raw2):
                    exec_lines = [ln.strip() for ln in raw2.splitlines() if ln.strip()][:3]
                    summary_source = "llm_retry"
        except Exception as e:
            logger.warning("executive summary LLM failed: %s", e)

    executive_summary = {
        "lines": exec_lines,
        "source": summary_source,
    }

    # --- 2 Scorecards
    scorecards = _scorecards(defects)

    # --- 3 Flow results
    flow_results: list[dict[str, Any]] = []
    for fl in flows:
        fds = fl.get("defects") if isinstance(fl.get("defects"), list) else []
        fd_list = [dict(x) for x in fds if isinstance(x, dict)]
        mc = _most_critical(fd_list)
        flow_results.append(
            {
                "flow_name": str(fl.get("name") or "unnamed"),
                "issues_count": len(fd_list),
                "most_critical_issue": mc,
                "metrics": fl.get("metrics") if isinstance(fl.get("metrics"), dict) else {},
            }
        )
    if not flow_results:
        flow_results = [
            {
                "flow_name": "pipeline",
                "issues_count": len(defects),
                "most_critical_issue": _most_critical(defects),
                "metrics": scan.get("metrics") if isinstance(scan.get("metrics"), dict) else {},
            }
        ]

    # --- 4 Defect list (async fix suggestions, bounded concurrency)
    sem = asyncio.Semaphore(4)

    async def _fix_one(d: Mapping[str, Any]) -> tuple[str, str]:
        fix = _rule_fix_suggestion(d)
        src = "rules"
        if not _llm_ready():
            return fix, src
        async with sem:
            try:
                llm_fix = await _llm_fix_suggestion(d)
                if llm_fix and len(llm_fix) > 12:
                    return llm_fix[:500], "llm"
            except Exception as e:
                logger.debug("fix suggestion LLM: %s", e)
        return fix, src

    fix_results = await asyncio.gather(*[_fix_one(d) for d in defects], return_exceptions=True)

    defect_list: list[dict[str, Any]] = []
    for i, d in enumerate(defects):
        sev = _normalize_severity(str(d.get("severity")))
        title = _defect_title(d)
        page = str(d.get("page_url") or "")
        impact = _infer_impact_bucket(d)
        ctx = _action_context_for_page(trail, page)
        shot = _screenshot_for_defect(d, trail)
        fr = fix_results[i] if i < len(fix_results) else None
        if isinstance(fr, tuple) and len(fr) == 2:
            fix, fix_source = fr
        else:
            fix, fix_source = _rule_fix_suggestion(d), "rules"
        defect_list.append(
            {
                "id": i,
                "severity": sev,
                "title": title,
                "page": page,
                "impact": impact,
                "action_context": ctx or "— no matching action_trail step for this page_url",
                "screenshot": shot or "— none referenced for this defect in payload",
                "fix_suggestion": fix,
                "fix_suggestion_source": fix_source,
            }
        )

    if not defect_list:
        defect_list = [
            {
                "id": 0,
                "severity": "n/a",
                "title": "No defects in merged payload",
                "page": str(scan.get("target_url") or "n/a"),
                "impact": "n/a",
                "action_context": f"— merged defect count=0; flows={len(flows)}",
                "screenshot": "—",
                "fix_suggestion": "Increase flow coverage or enable deeper checks — current payload had zero issues after dedupe.",
                "fix_suggestion_source": "rules",
            }
        ]

    # --- 5 Action trail
    action_trail_section = {
        "entries": trail,
        "count": len(trail),
        "note": "Chronological order by timestamp when present; else stable list order.",
    }

    # --- 6 Recommendations
    rec_items = _recommendations(defects, 10)
    if not rec_items:
        rec_items = [
            {
                "priority": 1,
                "severity": "n/a",
                "title": "No prioritized fixes — empty defect set",
                "page": str(scan.get("target_url") or ""),
                "impact": "n/a",
                "rationale": f"Zero defects after flatten/dedupe; action_trail length={len(trail)}.",
            }
        ]
    recommendations = {
        "items": rec_items,
        "count": len(rec_items),
    }

    # --- 6b Release decision (micro-task outcomes)
    shipping_decision = generate_decision(_task_results_from_scan(scan))

    # --- 7 Metadata
    started = scan.get("started_at")
    completed = scan.get("completed_at")
    ts = completed or started or datetime.now(timezone.utc).isoformat()
    visited = _pages_visited(scan, defects)
    metadata = {
        "pages_visited": visited,
        "pages_visited_count": len(visited),
        "actions_count": len(trail),
        "duration_seconds": scan.get("duration_seconds"),
        "flows": [str(f.get("name")) for f in flows if f.get("name")],
        "started_at": started,
        "completed_at": completed,
        "timestamp": ts,
        "target_url": str(scan.get("target_url") or ""),
    }

    return {
        "executive_summary": executive_summary,
        "scorecards": scorecards,
        "flow_results": flow_results,
        "defect_list": defect_list,
        "action_trail": action_trail_section,
        "recommendations": recommendations,
        "shipping_decision": shipping_decision,
        "metadata": metadata,
    }


def build_cto_report_sync(scan_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Sync wrapper for contexts without an event loop (runs ``asyncio.run``)."""
    return asyncio.run(build_cto_report(scan_payload))
