"""HTTP API for triggering QA runs."""

from __future__ import annotations

import asyncio
import sys

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import logging
import os
import time
import uuid
from uuid import UUID
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional

from dotenv import load_dotenv

load_dotenv()

# After .env: visible proof that API key is present (masked).
_llm_key_preview = (os.getenv("LLM_API_KEY") or "").strip()
print(
    "LLM CONFIG:",
    (_llm_key_preview[:5] if _llm_key_preview else "NOT SET"),
    flush=True,
)

from backend.services.llm_client import LLMClient, _is_placeholder_api_key

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared.models.config import FrameworkConfig

_logger = logging.getLogger(__name__)


def _coerce_scan_mode(v: str) -> Literal["fast", "deep"]:
    s = (v or "fast").strip().lower()
    return "deep" if s == "deep" else "fast"


def _llm_configured() -> bool:
    key = (os.environ.get("LLM_API_KEY") or "").strip()
    if not key or _is_placeholder_api_key(key):
        return False
    if not (os.environ.get("LLM_MODEL") or "").strip():
        return False
    if not (os.environ.get("LLM_BASE_URL") or "").strip():
        return False
    return True


async def _llm_verify_models_at_startup() -> None:
    """Confirm configured model ids exist on the provider (GET /models)."""
    try:
        llm = LLMClient()
        if not llm.api_key or not llm.base_url or _is_placeholder_api_key(llm.api_key):
            return
        await llm.verify_models()
    except Exception as e:
        print(f"WARNING: LLM model verification failed: {e}", flush=True)
        _logger.warning("LLM model verification failed: %s", e)


async def _llm_startup_smoke() -> None:
    """Optional one-shot completion (set LLM_STARTUP_SMOKE=1 to run)."""
    if (os.getenv("LLM_STARTUP_SMOKE") or "0").strip().lower() not in ("1", "true", "yes"):
        _logger.debug("LLM startup smoke skipped (set LLM_STARTUP_SMOKE=1 to enable)")
        return
    if not _llm_configured():
        _logger.info("LLM startup smoke skipped (LLM_API_KEY not set or placeholder)")
        return
    try:
        llm = LLMClient()
        if not (llm.api_key and llm.model and llm.base_url):
            print("LLM startup smoke: LLMClient missing env fields", flush=True)
            return
        out = await llm.complete(
            "You are a test assistant. Reply briefly.",
            'Reply with exactly one word: "pong"',
        )
        print("LLM startup smoke OK:", (out or "")[:300], flush=True)
    except Exception as e:
        print("LLM startup smoke FAILED:", e, flush=True)
        _logger.exception("LLM startup smoke failed")


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    await _llm_verify_models_at_startup()
    await _llm_startup_smoke()
    yield
    try:
        from backend.db.session import dispose_engine

        await dispose_engine()
    except Exception:
        pass


# App must be defined before middleware is applied.
app = FastAPI(title="Reqon AI API", version="0.1.0", lifespan=_app_lifespan)

# CORS for local dev / demo (frontend on a different port).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    url: str = Field(..., min_length=1)
    scan_mode: str = "fast"
    scan_task: str = "full_app_scan"
    browser_type: Optional[Literal["chromium", "firefox", "webkit"]] = Field(
        default=None,
        description="Playwright browser; omit for chromium.",
    )
    crawl_before_execution: bool = Field(
        default=False,
        description="If true, run site crawler for discovery before micro-task execution.",
    )
    flows: Optional[list[str]] = Field(
        default=None,
        description="Explicit flow ids (overrides scan_task when non-empty), e.g. search, coupon.",
    )
    task_type: Optional[str] = Field(
        default=None,
        description='Use "micro" with micro_task for a single fast task; omit for full scan.',
    )
    micro_task: Optional[str] = Field(
        default=None,
        description="Micro task id: search_product, add_to_cart, fill_checkout, contact_support, …",
    )
    auth: Optional[dict[str, Any]] = None
    requires_login: bool = False
    credentials: Optional[dict[str, Any]] = None
    task_input: Optional[str] = Field(
        default=None,
        description='Optional user intent, e.g. "search for shoes" → sets search_query when applicable.',
    )


class TestRunResponse(BaseModel):
    status: str = "started"
    job_id: str
    message: str = "Scan started"
    scan_mode: Literal["fast", "deep"] = "fast"
    scan_task: str = "full_app_scan"


class ResultsResponse(BaseModel):
    job_id: Optional[str] = None
    status: str
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    scan_mode: Optional[Literal["fast", "deep"]] = None
    scan_task: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    message: str
    progress: int


class ShareableReportResponse(BaseModel):
    """Minimal scan payload for shareable demo links."""

    report_id: str
    summary: Any = None
    issues: list[Any] = Field(default_factory=list)
    risk_score: float | int | None = None
    delta: dict[str, Any] | None = None


class SyntheticGenerateRequest(BaseModel):
    domain: str = Field(..., description="ecommerce | healthcare | finance | auth")
    count: int = Field(10, ge=1, le=1000)


# ---------------------------------------------------------------------
# In-memory job/result storage (simple, no DB)
# ---------------------------------------------------------------------
_jobs: dict[str, dict[str, Any]] = {}
_jobs_events: dict[str, list[dict[str, Any]]] = {}
_latest_job_id: str | None = None
_lock = asyncio.Lock()

# Last N completed runs (in-memory only; newest first).
_RUN_HISTORY_MAX = 10
_run_history: list[dict[str, Any]] = []
_total_runs_completed: int = 0

_STATUS_PROGRESS = {
    "QUEUED": 5,
    "RUNNING": 15,
    "WAITING_FOR_LOGIN": 25,
    "SCANNING": 60,
    "PARTIAL": 100,
    "COMPLETE": 100,
    "FAILED": 100,
}

# Real pipeline stage events advance progress (no fake timer).
_STAGE_PROGRESS_FROM_NAME: dict[str, int] = {
    "crawl_start": 18,
    "phase_1_crawling": 15,
    "crawl_complete": 35,
    "phase_2_execution": 40,
    "execution_start": 48,
    "execution_complete": 72,
    "phase_3_ai_analysis": 88,
    "phase_4_report": 95,
}


def _pipeline_event_message(kind: str, name: str, payload: dict[str, Any] | None) -> str:
    p = payload or {}
    if kind == "action" and name == "auth_message":
        return str(p.get("message") or "")
    if kind == "stage":
        if name == "phase_1_crawling":
            return str(p.get("banner") or "━━━ PHASE 1: CRAWLING ━━━")
        if name == "phase_2_execution":
            return str(p.get("banner") or "━━━ PHASE 2: EXECUTION ━━━")
        if name == "phase_3_ai_analysis":
            return str(p.get("banner") or "━━━ PHASE 3: AI ANALYSIS ━━━")
        if name == "phase_4_report":
            return str(p.get("banner") or "━━━ PHASE 4: REPORT ━━━")
        if name == "crawl_start":
            return "Starting site crawl"
        if name == "crawl_complete":
            n = p.get("pages")
            return f"Crawl complete ({n} pages)" if n is not None else "Crawl complete"
        if name == "execution_start":
            t = p.get("tests")
            return f"Running tests ({t} cases)" if t is not None else "Running tests"
        if name == "execution_complete":
            return (
                f"Tests finished — passed {p.get('passed', '?')}, failed {p.get('failed', '?')}"
            )
    if kind == "crawler":
        if name == "log":
            return str(p.get("message") or "")
        if name == "started":
            return "Crawler started"
        if name == "finished":
            n = p.get("pages")
            return f"Crawler finished ({n} pages)" if n is not None else "Crawler finished"
    if kind == "execution":
        if name == "test_start":
            return f"Test: {p.get('name', p.get('test_id', 'test'))}"
        if name == "qa_action":
            return str(p.get("message") or "")
        if name == "step":
            if p.get("message"):
                return str(p.get("message"))
            ph = p.get("phase", "step")
            at = p.get("action_type", "")
            return f"Step ({ph}) — {at}"
    if kind == "evaluator" and name == "retry":
        return (
            f"Evaluator retry — step {p.get('step_index', '')} "
            f"({p.get('phase', '')}) attempt {p.get('attempt', '')}"
        )
    return f"{kind}:{name}"


def _pipeline_timeout_seconds() -> float:
    """Max wall time for crawl+plan+execute (default 180s = 3 min)."""
    raw = (os.environ.get("SCAN_PIPELINE_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return 180.0
    try:
        return max(30.0, float(raw))
    except ValueError:
        return 180.0


async def _set_job_state(job_id: str, status: str, message: str) -> None:
    async with _lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = status
            _jobs[job_id]["status_message"] = message
            _jobs[job_id]["progress"] = _STATUS_PROGRESS.get(status, 0)


def _decision_from_result(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return "—"
    es = result.get("execution_snapshot")
    if isinstance(es, dict):
        d = es.get("decision")
        if d is not None and str(d).strip():
            return str(d).strip()
    return "—"


async def _append_run_history(job_id: str, url: str) -> None:
    """Record a terminal job in the ring buffer (newest first)."""
    global _total_runs_completed
    async with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        status = str(job.get("status") or "UNKNOWN")
        result = job.get("result")
        decision = _decision_from_result(result if isinstance(result, dict) else None)
        ts = float(job.get("completed_at") or job.get("started_at") or time.time())
        entry = {
            "job_id": job_id,
            "url": url,
            "decision": decision,
            "completed_at": ts,
            "status": status,
        }
        _run_history[:] = [e for e in _run_history if e.get("job_id") != job_id]
        _run_history.insert(0, entry)
        del _run_history[_RUN_HISTORY_MAX:]
        _total_runs_completed += 1

def _normalize_scan_task(raw: str | None) -> str:
    st = (raw or "full_app").strip().lower()
    if st in (
        "full_app",
        "full_app_scan",
        "quick_scan",
        "conversion_scan",
        "auth_scan",
        "auth",
        "checkout",
        "forms",
    ):
        return st
    return "full_app"


def _executive_summary_system_prompt(scan_task: str | None) -> str:
    """Task-aware system prompt: 2–3 sentences, business audience, no engineering jargon."""
    st = _normalize_scan_task(scan_task)
    core = (
        "You write very short executive summaries for business readers (product, leadership, commercial). "
        "Output 2–3 sentences only, plain text, no headings, bullets, markdown, or line breaks between sentences unless natural. "
        "Use only facts from the user message; do not invent URLs, page counts, or issue counts. "
        "Never mention HTML, DOM, CSS, selectors, the browser console, stack traces, or technical debugging steps. "
        "Emphasize shopper experience, trust, and revenue or conversion risk when the facts support it. "
        "Avoid corporate filler (e.g. robust, leverage, holistic, synergy, paradigm, moving forward, delve).\n\n"
    )
    focus = {
        "full_app": "Scope: broad site health — frame results as overall journey and revenue risk.\n",
        "full_app_scan": "Scope: full journey — breadth of coverage matters for leadership.\n",
        "quick_scan": "Scope: fast signal — stress timely risk to key pages, not exhaustive depth.\n",
        "conversion_scan": "Scope: purchase funnel — tie issues to carts, checkout, and lost sales.\n",
        "auth_scan": "Scope: sign-in and sessions — tie issues to account access and trust.\n",
        "auth": "Scope: authentication — tie issues to sign-in, session, and access risk.\n",
        "checkout": "Scope: checkout — tie issues to payment and order completion.\n",
        "forms": "Scope: forms — tie issues to data entry, submission, and customer confidence.\n",
    }
    return core + focus.get(st, focus["full_app"])


_SEVERITY_ORDER = ("critical", "high", "medium", "low")


def _issue_sort_key(issue: dict[str, Any]) -> tuple[int, str]:
    s = str(issue.get("severity") or "medium").strip().lower()
    try:
        idx = _SEVERITY_ORDER.index(s)
    except ValueError:
        idx = 2
    msg = str(issue.get("message") or "")
    return (idx, msg)


def _top_issues_for_summary(issues: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(issues, key=_issue_sort_key)
    return ranked[:n]


def _resolve_pages_scanned(result: dict[str, Any]) -> int:
    """Authoritative crawl page count: prefer ``pages`` length; never report 0 when that list is non-empty."""
    pages_list = result.get("pages")
    if isinstance(pages_list, list) and len(pages_list) > 0:
        return len(pages_list)
    summ = result.get("summary") or {}
    if not isinstance(summ, dict):
        summ = {}
    if result.get("pages_scanned") is not None:
        try:
            return max(0, int(result["pages_scanned"]))
        except (TypeError, ValueError):
            pass
    try:
        return max(0, int(summ.get("total_pages_scanned") or 0))
    except (TypeError, ValueError):
        return 0


def _summary_target_url(result: dict[str, Any], fallback: str) -> str:
    u = str(result.get("target_url") or "").strip()
    if u:
        return u
    pages = result.get("pages")
    if isinstance(pages, list) and pages:
        u0 = str((pages[0] or {}).get("url") or "").strip()
        if u0:
            return u0
    return (fallback or "").strip() or "unknown URL"


def _executive_summary_template_fields(
    issues: list[dict[str, Any]], url: str
) -> tuple[str, str, str, str]:
    """top_issue, page, business_impact, fix for the executive summary (plain-language)."""
    top = _top_issues_for_summary(issues, 1)
    if not top:
        return (
            "no issues detected",
            url,
            "no material revenue or experience risk surfaced in this pass",
            "No remediation required from this scan",
        )
    iss = top[0]
    title = str(iss.get("title") or "").strip()
    msg = str(iss.get("message") or "").strip()
    if title:
        top_issue = title[:400]
    elif msg:
        first = msg.split(". ")[0].strip()
        top_issue = first[:220] if len(first) <= 220 else msg[:180] + "…"
    else:
        top_issue = str(iss.get("type") or "a reported problem")[:200]
    page = str(iss.get("page_url") or "").strip() or url
    business_impact = (
        str(iss.get("business_impact") or "").strip()
        or "customer trust and conversion potential"
    )
    fix = str(iss.get("fix_suggestion") or "").strip() or (
        "Confirm on staging, fix the customer-visible behavior, then re-run this check."
    )
    return (top_issue, page, business_impact, fix)


def _render_executive_summary(
    url: str, pages_scanned: int, total_defects: int, issues: list[dict[str, Any]]
) -> str:
    top_issue, page, business_impact, fix = _executive_summary_template_fields(issues, url)
    if total_defects == 0 and not issues:
        return (
            f"This run reviewed {pages_scanned} page(s) on your site and did not surface issues that would "
            f"clearly hurt shoppers or revenue. Experience risk looks low from this pass; validate again after major releases."
        )
    return (
        f"We reviewed {pages_scanned} page(s) and found {total_defects} issue(s) that could affect "
        f"experience or sales if ignored. The top concern is {top_issue} (seen on {page}). "
        f"{business_impact} Next step: {fix}"
    )


def _executive_summary_facts(
    result: dict[str, Any],
) -> tuple[int, int, dict[str, int], list[str]]:
    """Pages scanned, defect total, per-severity counts, distinct business_impact tags."""
    summ = result.get("summary") or {}
    if not isinstance(summ, dict):
        summ = {}
    pages = _resolve_pages_scanned(result)
    issues = list(result.get("issues") or [])
    raw_total = summ.get("total_issues_found")
    if raw_total is not None:
        try:
            n_defects = int(raw_total)
        except (TypeError, ValueError):
            n_defects = len(issues)
    else:
        n_defects = len(issues)
    ibs = result.get("issues_by_severity") or {}
    if not isinstance(ibs, dict):
        ibs = {}
    sev_counts: dict[str, int] = {}
    for k in ("critical", "high", "medium", "low"):
        v = ibs.get(k)
        sev_counts[k] = len(v) if isinstance(v, list) else 0
    impacts = sorted(
        {
            str(i.get("business_impact") or "").strip()
            for i in issues
            if (i.get("business_impact") or "").strip()
        }
    )
    return pages, n_defects, sev_counts, impacts


def _trend_context(result: dict[str, Any]) -> str:
    dr = result.get("delta_report")
    if isinstance(dr, dict) and dr.get("compared_to_scan_id") is not None:
        rc = dr.get("risk_change")
        ni = dr.get("new_issues")
        ri = dr.get("resolved_issues")
        td = dr.get("trend_direction")
        pr = dr.get("previous_risk_score")
        cr = dr.get("current_risk_score")
        parts = [
            f"Versus last scan: risk {pr}→{cr} (change {rc!r})",
            f"; defect churn: +{ni} new signatures, −{ri} resolved",
        ]
        if td == "worse":
            parts.append(" — APP REGRESSED vs last scan (higher risk; treat as urgent).")
        elif td == "better":
            parts.append(" — risk improved vs last scan.")
        elif td == "stable":
            parts.append(" — risk flat vs last scan.")
        return "".join(parts)
    if isinstance(dr, dict) and dr.get("recent_scans") and dr.get("compared_to_scan_id") is None:
        return (
            "No prior scan in database to compare; this payload may be the first stored run for this URL."
        )
    if result.get("trend") is not None:
        return str(result["trend"])
    prev = result.get("previous_risk_score")
    if prev is not None and result.get("risk_score") is not None:
        try:
            delta = int(result["risk_score"]) - int(prev)
            return f"Risk score changed by {delta:+d} vs prior run (approximate trend)."
        except (TypeError, ValueError):
            pass
    cov = result.get("coverage")
    if isinstance(cov, dict) and cov.get("overall") is not None:
        return (
            f"Coverage health snapshot: {cov.get('overall')} "
            "(no historical comparison in this payload)."
        )
    return "No trend or prior-run comparison available for this scan."


def _build_executive_summary_user_prompt(
    result: dict[str, Any], url: str, *, scan_task: str | None = None
) -> str:
    issues = list(result.get("issues") or [])
    pages, n_def, sev, impact_tags = _executive_summary_facts(result)
    top_issue, page, bi, fix = _executive_summary_template_fields(issues, url)
    st = _normalize_scan_task(scan_task or str(result.get("scan_task") or ""))
    pm_raw = result.get("pipeline_metrics")
    pm = pm_raw if isinstance(pm_raw, dict) else {}
    exec_focus = str(pm.get("task") or "").strip()
    lines: list[str] = [
        "Write 2–3 sentences for business stakeholders. Plain English; no engineering or debugging jargon.",
        "",
        f"Scan preset: {st}."
        + (f" Executed checks: {exec_focus}." if exec_focus else ""),
        f"Site: {url}",
        f"Pages reviewed: {pages}",
        f"Issues found: {n_def}",
        f"Severity — critical: {sev['critical']}, high: {sev['high']}, "
        f"medium: {sev['medium']}, low: {sev['low']}",
    ]
    if issues:
        lines.extend(
            [
                f"Top issue (plain language): {top_issue}",
                f"Where: {page}",
                f"Business impact: {bi}",
                f"Suggested action: {fix}",
            ]
        )
    lines.extend(
        [
            f"Business-impact tags: {', '.join(impact_tags) if impact_tags else '(none)'}",
            f"Trend / comparison: {_trend_context(result)}",
        ]
    )
    return "\n".join(lines)


def _fallback_executive_summary(result: dict[str, Any], issues: list[dict[str, Any]], url: str) -> str:
    pages, n_def, _, _ = _executive_summary_facts(result)
    if pages == 0:
        return ""
    return _render_executive_summary(url, pages, n_def, issues)


async def _generate_executive_summary(job_id: str, request_url: str = "") -> None:
    async with _lock:
        job = _jobs.get(job_id)
        result = (job or {}).get("result") if job else None
        if not isinstance(result, dict):
            return
        issues = list(result.get("issues") or [])
        result_snapshot = dict(result)
        url = _summary_target_url(result_snapshot, request_url)
        scan_task = _normalize_scan_task(
            str((job or {}).get("scan_task") or result_snapshot.get("scan_task") or "")
        )

    if _resolve_pages_scanned(result_snapshot) == 0:
        async with _lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "FAILED"
                _jobs[job_id]["status_message"] = "Scan failed: no pages were crawled"
                if not str(_jobs[job_id].get("error") or "").strip():
                    _jobs[job_id]["error"] = "No pages scanned"
                res = _jobs[job_id].get("result")
                if isinstance(res, dict):
                    res.pop("executive_summary", None)
        return

    if not _llm_configured():
        summary = _fallback_executive_summary(result_snapshot, issues, url)
    else:
        try:
            llm = LLMClient()
            user_prompt = _build_executive_summary_user_prompt(
                result_snapshot, url, scan_task=scan_task
            )
            summary = await llm.complete(
                system_prompt=_executive_summary_system_prompt(scan_task),
                user_prompt=user_prompt,
            )
            summary = (summary or "").strip() or _fallback_executive_summary(
                result_snapshot, issues, url
            )
        except Exception:
            summary = _fallback_executive_summary(result_snapshot, issues, url)

    async with _lock:
        if job_id in _jobs and isinstance(_jobs[job_id].get("result"), dict):
            _jobs[job_id]["result"]["executive_summary"] = summary


async def _push_event(
    job_id: str,
    event_type: str,
    message: str,
    *,
    name: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    async with _lock:
        if job_id not in _jobs_events:
            _jobs_events[job_id] = []
        entry: dict[str, Any] = {
            "time": time.time(),
            "type": event_type,
            "message": message,
        }
        if name is not None:
            entry["name"] = name
        if payload:
            entry["payload"] = payload
        _jobs_events[job_id].append(entry)


async def _apply_stage_progress(job_id: str, kind: str, name: str) -> None:
    if kind != "stage":
        return
    pct = _STAGE_PROGRESS_FROM_NAME.get(name)
    if pct is None:
        return
    async with _lock:
        if job_id in _jobs:
            cur = int(_jobs[job_id].get("progress", 0))
            _jobs[job_id]["progress"] = max(cur, pct)


async def _pipeline_emit(
    job_id: str, kind: str, name: str, payload: dict[str, Any] | None = None
) -> None:
    msg = _pipeline_event_message(kind, name, payload)
    await _push_event(job_id, kind, msg, name=name, payload=payload)
    await _apply_stage_progress(job_id, kind, name)
    if kind == "stage" and name in ("crawl_start", "phase_1_crawling"):
        await _set_job_state(job_id, "SCANNING", "Crawling site")


@app.post("/jobs/test.run", response_model=TestRunResponse)
async def trigger_test_run(req: ScanRequest) -> Any:
    """Kick off a run and return a job handle immediately."""
    global _latest_job_id

    job_id = f"job_{uuid.uuid4().hex[:10]}"
    started_at = time.time()

    async with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "QUEUED",
            "status_message": "Job queued",
            "progress": _STATUS_PROGRESS["QUEUED"],
            "started_at": started_at,
            "completed_at": None,
            "result": None,
            "error": None,
            "scan_mode": _coerce_scan_mode(req.scan_mode),
            "scan_task": (req.scan_task or "full_app_scan").strip() or "full_app_scan",
        }
        _jobs_events[job_id] = []
        _latest_job_id = job_id
    await _push_event(job_id, "action", "Job queued")

    async def _run_job() -> None:
        try:
            await _set_job_state(job_id, "RUNNING", "Starting scan run")
            await _push_event(job_id, "action", "Opening browser")
            await _push_event(job_id, "action", "Loading URL")
            await _push_event(job_id, "detection", "Detecting login form")

            # Lazy import so the API can start even if Playwright isn't installed yet.
            from backend.orchestrator import Orchestrator

            sm = _coerce_scan_mode(req.scan_mode)
            st = (req.scan_task or "full_app_scan").strip() or "full_app_scan"
            creds: dict[str, Any] | None = None
            if req.requires_login and req.credentials and isinstance(req.credentials, dict):
                creds = {str(k): str(v) for k, v in req.credentials.items() if v is not None}
            flow_list: list[str] | None = None
            if req.flows and isinstance(req.flows, list) and len(req.flows) > 0:
                flow_list = [str(x).strip() for x in req.flows if str(x).strip()]
            tt = (req.task_type or "").strip() or None
            mt = (req.micro_task or "").strip() or None
            bt = req.browser_type or "chromium"
            ti = (req.task_input or "").strip() or None
            config = FrameworkConfig(
                target_url=req.url,
                scan_mode=sm,
                scan_task=st,
                flows=flow_list,
                task_type=tt,
                micro_task=mt,
                browser_type=bt,
                crawl_before_execution=bool(req.crawl_before_execution),
                task_input=ti,
                requires_login=bool(req.requires_login),
                credentials=creds,
            )
            auth_username = auth_password = ""
            if req.auth and isinstance(req.auth, dict):
                auth_username = str(req.auth.get("username") or "").strip()
                auth_password = str(req.auth.get("password") or "").strip()
            if auth_username and auth_password:
                await _set_job_state(
                    job_id,
                    "WAITING_FOR_LOGIN",
                    "Please login in the Chrome window",
                )
                config.auth = {
                    "login_url": req.url,
                    "username": auth_username,
                    "password": auth_password,
                    "auto_detect": True,
                }
                await _push_event(job_id, "detection", "Login page detected")
                await _push_event(job_id, "action", "⏸ Waiting for you to login in the browser window...")

            async def emit_bridge(
                kind: str, name: str, payload: dict[str, Any] | None = None
            ) -> None:
                await _pipeline_emit(job_id, kind, name, payload)

            orch = Orchestrator(config, emit=emit_bridge, job_id=job_id)

            # Guard against stalled pipelines.
            result = await asyncio.wait_for(
                orch._run_pipeline(),
                timeout=_pipeline_timeout_seconds(),
            )
            issues_found = int(((result or {}).get("summary") or {}).get("total_issues_found") or 0)
            if issues_found > 0:
                await _push_event(job_id, "success", f"Found {issues_found} issues")
            auth_status = str((result or {}).get("auth_status") or "not_attempted")
            if auth_status == "success":
                await _set_job_state(job_id, "SCANNING", "Login confirmed, scanning in progress")
                await _push_event(job_id, "success", "Login confirmed — resuming scan")
                await _push_event(job_id, "success", "Login successful")
            if auth_status == "failed":
                issues = list((result or {}).get("issues") or [])
                login_timeout = any("timeout" in str(i.get("message", "")).lower() for i in issues)
                await _push_event(
                    job_id,
                    "error",
                    "Login timeout — scan cancelled" if login_timeout else "Login failed — check credentials or bot protection",
                )
            if bool((result or {}).get("partial")):
                await _push_event(job_id, "detection", "Scan marked as partial")

            pages_n = _resolve_pages_scanned(result or {})
            if pages_n == 0:
                await _push_event(job_id, "error", "No pages were crawled — scan failed")
                async with _lock:
                    if job_id in _jobs:
                        _jobs[job_id]["completed_at"] = time.time()
                        _jobs[job_id]["result"] = result
                        _jobs[job_id]["error"] = "No pages scanned"
                await _set_job_state(job_id, "FAILED", "Scan failed: no pages were crawled")
            else:
                await _push_event(job_id, "action", "Generating AI summary...")
                await _push_event(job_id, "success", "Scan complete")

                async with _lock:
                    if job_id in _jobs:
                        _jobs[job_id]["completed_at"] = time.time()
                        _jobs[job_id]["result"] = result
                await _set_job_state(
                    job_id,
                    "PARTIAL" if bool((result or {}).get("partial")) else "COMPLETE",
                    "Scan finished with partial results"
                    if bool((result or {}).get("partial"))
                    else "Scan completed successfully",
                )
                asyncio.create_task(_generate_executive_summary(job_id, req.url))
        except asyncio.TimeoutError:
            await _push_event(job_id, "error", "Scan timeout")
            partial_result = await orch.build_partial_result("Scan timed out — showing partial results")
            try:
                from backend.db.persistence import persist_pipeline_result

                _sid, delta_report, _rid = await persist_pipeline_result(
                    req.url,
                    partial_result,
                    orch._last_site_model,
                    orch._last_run_result,
                )
                if delta_report is not None:
                    partial_result["delta_report"] = delta_report
            except Exception:
                pass
            try:
                from backend.services.decision_insights import attach_decision_insights
                from backend.services.risk_explanation import attach_risk_explanation

                await attach_risk_explanation(partial_result)
                await attach_decision_insights(partial_result)
            except Exception:
                pass
            async with _lock:
                if job_id in _jobs:
                    _jobs[job_id]["completed_at"] = time.time()
                    _jobs[job_id]["error"] = "Scan timeout"
                    _jobs[job_id]["result"] = partial_result
            if _resolve_pages_scanned(partial_result) == 0:
                async with _lock:
                    if job_id in _jobs:
                        _jobs[job_id]["error"] = "Scan timed out — no pages crawled"
                await _set_job_state(job_id, "FAILED", "Scan failed: no pages were crawled")
            else:
                await _set_job_state(job_id, "PARTIAL", "Scan timed out — showing partial results")
        except Exception as e:
            await _push_event(job_id, "error", f"Scan failed: {e}")
            async with _lock:
                if job_id in _jobs:
                    _jobs[job_id]["completed_at"] = time.time()
                    _jobs[job_id]["error"] = str(e)
                    _jobs[job_id]["result"] = None
            await _set_job_state(job_id, "FAILED", "Scan failed")
        finally:
            # Never leave a job in pending/running forever.
            forced_failed = False
            async with _lock:
                job = _jobs.get(job_id)
                if job and job.get("status") in {"QUEUED", "RUNNING"}:
                    job["completed_at"] = time.time()
                    job["error"] = job.get("error") or "Scan ended unexpectedly"
                    # No fabricated scan payload — result stays unset/None unless a real pipeline wrote it.
                    forced_failed = True
            if forced_failed:
                await _set_job_state(job_id, "FAILED", "Scan ended unexpectedly")
            async with _lock:
                status = (_jobs.get(job_id) or {}).get("status")
            if status == "COMPLETE":
                await _push_event(job_id, "success", "SCAN COMPLETE")
            elif status == "PARTIAL":
                await _push_event(job_id, "detection", "Job completed with partial results")
            elif status == "FAILED":
                await _push_event(job_id, "error", "Job failed")

            await _append_run_history(job_id, req.url)

    asyncio.create_task(_run_job())

    return TestRunResponse(
        job_id=job_id,
        scan_mode=_coerce_scan_mode(req.scan_mode),
        scan_task=(req.scan_task or "full_app_scan").strip() or "full_app_scan",
    )


@app.get("/report/{report_id}", response_model=ShareableReportResponse)
async def get_shareable_report(report_id: UUID) -> ShareableReportResponse:
    """Load a persisted scan snapshot by id (shareable demo link). Requires DATABASE_URL."""
    from backend.db.persistence import fetch_report_by_id

    payload = await fetch_report_by_id(str(report_id))
    if not payload:
        raise HTTPException(status_code=404, detail="report not found")
    return ShareableReportResponse(
        report_id=str(payload.get("report_id") or report_id),
        summary=payload.get("summary"),
        issues=list(payload.get("issues") or []),
        risk_score=payload.get("risk_score"),
        delta=payload.get("delta"),
    )


@app.post("/synthetic/generate")
async def generate_synthetic(req: SyntheticGenerateRequest) -> dict[str, Any]:
    """Generate synthetic domain data for demos/testing."""
    try:
        from faker import Faker

        fake = Faker()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Faker is not available: {e}")

    domain = req.domain.strip().lower()
    count = req.count

    if domain not in {"ecommerce", "healthcare", "finance", "auth"}:
        raise HTTPException(
            status_code=400,
            detail="domain must be one of: ecommerce, healthcare, finance, auth",
        )

    rows: list[dict[str, Any]] = []
    for _ in range(count):
        if domain == "ecommerce":
            rows.append(
                {
                    "product_name": fake.catch_phrase(),
                    "price": round(fake.pyfloat(min_value=5, max_value=1500, right_digits=2), 2),
                    "sku": fake.bothify(text="SKU-####-??"),
                    "stock": fake.random_int(min=0, max=500),
                }
            )
        elif domain == "healthcare":
            rows.append(
                {
                    "patient_name": fake.name(),
                    "dob": fake.date_of_birth(minimum_age=1, maximum_age=95).isoformat(),
                    "diagnosis": fake.random_element(
                        [
                            "Hypertension",
                            "Type 2 Diabetes",
                            "Seasonal Allergy",
                            "Anxiety Disorder",
                            "Migraine",
                        ]
                    ),
                }
            )
        elif domain == "finance":
            rows.append(
                {
                    "account_number": fake.bban(),
                    "transaction_amount": round(
                        fake.pyfloat(min_value=1, max_value=20000, right_digits=2), 2
                    ),
                    "currency": fake.random_element(["USD", "EUR", "GBP", "JPY"]),
                }
            )
        else:  # auth
            rows.append(
                {
                    "email": fake.email(),
                    "username": fake.user_name(),
                    "password": fake.password(length=12, special_chars=True, digits=True),
                    "role": fake.random_element(["admin", "analyst", "viewer"]),
                }
            )

    return {
        "domain": domain,
        "count": count,
        "rows": rows,
    }


@app.get("/dashboard/summary")
async def get_dashboard_summary() -> dict[str, Any]:
    """Lightweight stats for the home dashboard (single request)."""
    async with _lock:
        last = _run_history[0] if _run_history else None
        pass_n = sum(
            1 for e in _run_history if str(e.get("status")) in ("COMPLETE", "PARTIAL")
        )
        fail_n = sum(1 for e in _run_history if str(e.get("status")) == "FAILED")
        return {
            "total_runs": _total_runs_completed,
            "last_decision": last.get("decision") if last else None,
            "last_job_id": last.get("job_id") if last else None,
            "pass_count": pass_n,
            "fail_count": fail_n,
        }


@app.get("/runs/history")
async def get_run_history() -> dict[str, Any]:
    """Last 10 completed runs (in-memory; no persistence)."""
    async with _lock:
        return {"runs": list(_run_history)}


@app.get("/results", response_model=ResultsResponse)
async def get_latest_results() -> Any:
    """Return the latest job status and (if available) its results."""
    async with _lock:
        if not _latest_job_id:
            return ResultsResponse(status="none", result=None)
        data = _jobs.get(_latest_job_id)
        if not data:
            return ResultsResponse(status="none", result=None)
        return ResultsResponse(
            job_id=data.get("job_id"),
            status=str(data.get("status", "unknown")).lower(),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
            scan_mode=data.get("scan_mode"),
            scan_task=data.get("scan_task"),
        )


@app.get("/results/{job_id}", response_model=ResultsResponse)
async def get_results(job_id: str) -> Any:
    """Return a specific job's status/results."""
    async with _lock:
        data = _jobs.get(job_id)
        if not data:
            raise HTTPException(status_code=404, detail="job not found")
        return ResultsResponse(
            job_id=data.get("job_id"),
            status=str(data.get("status", "unknown")).lower(),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
            scan_mode=data.get("scan_mode"),
            scan_task=data.get("scan_task"),
        )


@app.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> Any:
    async with _lock:
        data = _jobs.get(job_id)
        if not data:
            raise HTTPException(status_code=404, detail="job not found")
        return JobStatusResponse(
            job_id=data.get("job_id", job_id),
            status=str(data.get("status", "QUEUED")),
            message=str(data.get("status_message", "")),
            progress=int(data.get("progress", 0)),
        )


@app.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str) -> dict[str, Any]:
    async with _lock:
        if job_id not in _jobs:
            raise HTTPException(status_code=404, detail="job not found")
        return {"job_id": job_id, "events": list(_jobs_events.get(job_id, []))}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ═══════════════════════════════════════════════
# NISCHAY AI FRONTEND BRIDGE — NEW ENDPOINTS
# Appended below existing code — nothing above modified
# ═══════════════════════════════════════════════

# New imports for frontend bridge endpoints
from pathlib import Path
import time as _time
import json as _json

from fastapi.responses import StreamingResponse

from pydantic import BaseModel as _BaseModel, Field as _Field

from shared.models.config import ViewportConfig
from shared.models.run_record import RunRecord

import api.run_store as run_store

from backend.core.task_registry import LEGACY_FLOW_TO_TASKS, TASK_GROUPS


def _map_frontend_module_to_flow(mid: str) -> str:
    m = (mid or "").strip().lower()
    aliases = {
        "product_pages": "product",
        "links_assets": "navigation",
    }
    return aliases.get(m, m)


def _depth_to_scan_task(depth: str, modules: list[str]) -> tuple[str, list[str] | None]:
    """Return (scan_task, flows_override)."""
    if modules and len(modules) > 0:
        flows = [_map_frontend_module_to_flow(x) for x in modules]
        return ("full_app_scan", flows)
    d = (depth or "standard").strip().lower()
    if d == "quick":
        return ("quick_scan", None)
    if d == "deep":
        return ("full_app_scan", None)
    return ("conversion_scan", None)


def _device_viewport(device: str) -> ViewportConfig:
    dv = (device or "desktop").strip().lower()
    if dv == "mobile":
        return ViewportConfig(width=390, height=844, name="mobile")
    if dv == "tablet":
        return ViewportConfig(width=768, height=1024, name="tablet")
    return ViewportConfig(width=1280, height=720, name="desktop")


class ApiRunBody(_BaseModel):
    """POST /api/run JSON body from Nischay AI frontend."""

    url: str = _Field(..., min_length=1)
    depth: str = "standard"
    modules: list[str] = _Field(default_factory=list)
    tasks: list[str] = _Field(default_factory=list)
    device: str = "desktop"
    auth: dict[str, Any] | None = None


def _api_run_body_to_scan_request(body: ApiRunBody) -> ScanRequest:
    scan_task, flows = _depth_to_scan_task(body.depth, list(body.modules or []))
    task_input = "\n".join([str(t).strip() for t in (body.tasks or []) if str(t).strip()])
    sm = _coerce_scan_mode("deep" if (body.depth or "").lower() == "deep" else "fast")
    creds: dict[str, Any] | None = None
    auth_block: dict[str, Any] | None = None
    if body.auth and isinstance(body.auth, dict):
        email = str(body.auth.get("email") or body.auth.get("username") or "").strip()
        password = str(body.auth.get("password") or "").strip()
        if email and password:
            creds = {"username": email, "password": password}
            auth_block = {"username": email, "password": password}
    return ScanRequest(
        url=str(body.url).strip(),
        scan_mode=sm,
        scan_task=scan_task,
        flows=flows,
        crawl_before_execution=False,
        task_input=task_input or None,
        requires_login=bool(creds),
        credentials=creds,
        auth=auth_block,
        browser_type="chromium",
    )


async def _save_api_run_config(run_id: str, body: ApiRunBody) -> None:
    path = run_store.run_dir(run_id) / "api_run_config.json"

    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "url": body.url,
            "depth": body.depth,
            "modules": list(body.modules or []),
            "tasks": list(body.tasks or []),
            "device": body.device,
            "auth": body.auth,
        }
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(payload, f, indent=2, default=str)

    await asyncio.to_thread(_write)


def _run_status_to_frontend(job_status: str) -> str:
    s = str(job_status or "").upper()
    if s in ("QUEUED", "RUNNING", "WAITING_FOR_LOGIN", "SCANNING"):
        return "running"
    if s in ("COMPLETE", "PARTIAL"):
        return "completed"
    if s == "FAILED":
        return "failed"
    return "pending"


def _infer_stage_from_message(msg: str) -> str:
    m = (msg or "").lower()
    if "phase 1" in m or "crawling" in m or "crawl" in m or "crawler" in m:
        return "crawl"
    if "phase 2" in m or "execution" in m or "running tests" in m:
        return "execute"
    if "phase 3" in m or "ai analysis" in m:
        return "detect"
    if "phase 4" in m or "report" in m:
        return "report"
    if "generating ai summary" in m:
        return "score"
    if "plan" in m:
        return "plan"
    if "detect" in m:
        return "detect"
    if "score" in m or "risk" in m:
        return "score"
    return "execute"


def _bridge_compute_metrics(result: dict[str, Any] | None) -> tuple[int, int, int]:
    if not isinstance(result, dict):
        return 0, 0, 0
    summ = result.get("summary") or {}
    if not isinstance(summ, dict):
        summ = {}
    pages = int(summ.get("total_pages_scanned") or result.get("pages_scanned") or 0)
    try:
        pages = max(0, pages)
    except (TypeError, ValueError):
        pages = 0
    actions = int(summ.get("total_actions_run") or 0)
    try:
        actions = max(0, actions)
    except (TypeError, ValueError):
        actions = 0
    issues = int(summ.get("total_issues_found") or len(result.get("issues") or []) or 0)
    try:
        issues = max(0, issues)
    except (TypeError, ValueError):
        issues = 0
    return pages, actions, issues


async def _bridge_run_status_payload(run_key: str) -> dict[str, Any]:
    """run_key: same string for run_id and job_id in bridge mode."""
    async with _lock:
        job = _jobs.get(run_key)
    started = float((job or {}).get("started_at") or _time.time())
    completed = (job or {}).get("completed_at")
    elapsed = 0.0
    if isinstance(completed, (int, float)):
        elapsed = max(0.0, float(completed) - float(started))
    elif job:
        elapsed = max(0.0, _time.time() - float(started))

    result = (job or {}).get("result") if job else None
    pages, actions, issues = _bridge_compute_metrics(result if isinstance(result, dict) else None)
    risk_score = None
    risk_level = None
    if isinstance(result, dict):
        rs = result.get("risk_score")
        try:
            risk_score = int(rs) if rs is not None else None
        except (TypeError, ValueError):
            risk_score = None
        rl = result.get("risk_level")
        risk_level = str(rl) if rl is not None else None

    stage = "crawl"
    progress = int((job or {}).get("progress") or 0)
    current_action = ""
    async with _lock:
        evs = list(_jobs_events.get(run_key, []))
    if evs:
        last = evs[-1]
        current_action = str(last.get("message") or "")
        stage = _infer_stage_from_message(current_action)

    jstat = str((job or {}).get("status") or "QUEUED")
    if jstat in ("COMPLETE", "PARTIAL") and isinstance(result, dict):
        stage = "done"
    elif jstat == "FAILED":
        stage = "done"

    return {
        "run_id": run_key,
        "status": _run_status_to_frontend(jstat),
        "stage": stage,
        "progress": min(100, max(0, progress)),
        "current_action": current_action,
        "pages_found": pages,
        "actions_run": actions,
        "issues_found": issues,
        "elapsed_seconds": int(elapsed),
        "risk_score": risk_score,
        "risk_level": risk_level,
    }


def _parse_log_timestamp(line: str) -> float | None:
    s = (line or "").strip()
    if len(s) >= 20 and s[0] == "[" and "]" in s[:30]:
        try:
            from datetime import datetime, timezone

            inner = s[1 : s.index("]")]
            dt = datetime.fromisoformat(inner.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return None
    return None


def _merge_run_log_lines(run_id: str) -> list[str]:
    """Merge logs.txt + console_logs.txt; dedupe; sort by timestamp when present."""
    root = run_store.run_dir(run_id)
    p1 = root / "logs.txt"
    p2 = root / "console_logs.txt"
    lines: list[str] = []
    for p in (p1, p2):
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ln in text.splitlines():
            t = ln.strip()
            if t:
                lines.append(t)
    seen: set[str] = set()
    uniq: list[str] = []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            uniq.append(ln)

    def sort_key(line: str) -> tuple[float, int]:
        ts = _parse_log_timestamp(line)
        return (ts if ts is not None else 0.0, hash(line) % 10_000_000)

    return sorted(uniq, key=sort_key)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check for Nischay AI frontend (includes API version)."""
    return {"status": "ok", "version": getattr(app, "version", None) or "0.1.0"}


@app.post("/api/run")
async def api_run(body: ApiRunBody) -> dict[str, Any]:
    """Start a QA run using the same pipeline as /jobs/test.run; returns run_id == job_id."""
    global _latest_job_id

    unified_id = f"run_{uuid.uuid4().hex[:10]}"
    req = _api_run_body_to_scan_request(body)
    started_at = _time.time()

    async with _lock:
        _jobs[unified_id] = {
            "job_id": unified_id,
            "status": "QUEUED",
            "status_message": "Job queued",
            "progress": _STATUS_PROGRESS["QUEUED"],
            "started_at": started_at,
            "completed_at": None,
            "result": None,
            "error": None,
            "scan_mode": _coerce_scan_mode(req.scan_mode),
            "scan_task": (req.scan_task or "full_app_scan").strip() or "full_app_scan",
        }
        _jobs_events[unified_id] = []
        _latest_job_id = unified_id
    await _push_event(unified_id, "action", "Job queued")

    await run_store.create_run(unified_id, unified_id, str(body.url).strip())
    await _save_api_run_config(unified_id, body)

    async def _run_job_bridge() -> None:
        orch: Any = None
        try:
            await _set_job_state(unified_id, "RUNNING", "Starting scan run")
            await _push_event(unified_id, "action", "Opening browser")
            await _push_event(unified_id, "action", "Loading URL")
            await _push_event(unified_id, "detection", "Detecting login form")

            from backend.orchestrator import Orchestrator

            sm = _coerce_scan_mode(req.scan_mode)
            st = (req.scan_task or "full_app_scan").strip() or "full_app_scan"
            creds: dict[str, Any] | None = None
            if req.requires_login and req.credentials and isinstance(req.credentials, dict):
                creds = {str(k): str(v) for k, v in req.credentials.items() if v is not None}
            flow_list: list[str] | None = None
            if req.flows and isinstance(req.flows, list) and len(req.flows) > 0:
                flow_list = [str(x).strip() for x in req.flows if str(x).strip()]
            tt = (req.task_type or "").strip() or None
            mt = (req.micro_task or "").strip() or None
            bt = req.browser_type or "chromium"
            ti = (req.task_input or "").strip() or None
            config = FrameworkConfig(
                target_url=req.url,
                scan_mode=sm,
                scan_task=st,
                flows=flow_list,
                task_type=tt,
                micro_task=mt,
                browser_type=bt,
                crawl_before_execution=bool(req.crawl_before_execution),
                task_input=ti,
                requires_login=bool(req.requires_login),
                credentials=creds,
            )
            try:
                config.crawl.viewport = _device_viewport(body.device)
            except Exception:
                pass
            auth_username = auth_password = ""
            if req.auth and isinstance(req.auth, dict):
                auth_username = str(req.auth.get("username") or "").strip()
                auth_password = str(req.auth.get("password") or "").strip()
            if auth_username and auth_password:
                await _set_job_state(
                    unified_id,
                    "WAITING_FOR_LOGIN",
                    "Please login in the Chrome window",
                )
                config.auth = {
                    "login_url": req.url,
                    "username": auth_username,
                    "password": auth_password,
                    "auto_detect": True,
                }
                await _push_event(unified_id, "detection", "Login page detected")
                await _push_event(
                    unified_id,
                    "action",
                    "⏸ Waiting for you to login in the browser window...",
                )

            async def emit_bridge(
                kind: str, name: str, payload: dict[str, Any] | None = None
            ) -> None:
                await _pipeline_emit(unified_id, kind, name, payload)

            orch = Orchestrator(config, emit=emit_bridge, job_id=unified_id)

            result = await asyncio.wait_for(
                orch._run_pipeline(),
                timeout=_pipeline_timeout_seconds(),
            )
            issues_found = int(((result or {}).get("summary") or {}).get("total_issues_found") or 0)
            if issues_found > 0:
                await _push_event(unified_id, "success", f"Found {issues_found} issues")
            auth_status = str((result or {}).get("auth_status") or "not_attempted")
            if auth_status == "success":
                await _set_job_state(unified_id, "SCANNING", "Login confirmed, scanning in progress")
                await _push_event(unified_id, "success", "Login confirmed — resuming scan")
                await _push_event(unified_id, "success", "Login successful")
            if auth_status == "failed":
                issues = list((result or {}).get("issues") or [])
                login_timeout = any(
                    "timeout" in str(i.get("message", "")).lower() for i in issues
                )
                await _push_event(
                    unified_id,
                    "error",
                    "Login timeout — scan cancelled"
                    if login_timeout
                    else "Login failed — check credentials or bot protection",
                )
            if bool((result or {}).get("partial")):
                await _push_event(unified_id, "detection", "Scan marked as partial")

            pages_n = _resolve_pages_scanned(result or {})
            if pages_n == 0:
                await _push_event(unified_id, "error", "No pages were crawled — scan failed")
                async with _lock:
                    if unified_id in _jobs:
                        _jobs[unified_id]["completed_at"] = _time.time()
                        _jobs[unified_id]["result"] = result
                        _jobs[unified_id]["error"] = "No pages scanned"
                await _set_job_state(unified_id, "FAILED", "Scan failed: no pages were crawled")
                await run_store.finalize_run(
                    unified_id,
                    status="failed",
                    result=result if isinstance(result, dict) else None,
                    error="No pages scanned",
                    partial=False,
                )
            else:
                await _push_event(unified_id, "action", "Generating AI summary...")
                await _push_event(unified_id, "success", "Scan complete")

                async with _lock:
                    if unified_id in _jobs:
                        _jobs[unified_id]["completed_at"] = _time.time()
                        _jobs[unified_id]["result"] = result
                await _set_job_state(
                    unified_id,
                    "PARTIAL" if bool((result or {}).get("partial")) else "COMPLETE",
                    "Scan finished with partial results"
                    if bool((result or {}).get("partial"))
                    else "Scan completed successfully",
                )
                asyncio.create_task(_generate_executive_summary(unified_id, req.url))
                await run_store.finalize_run(
                    unified_id,
                    status="success",
                    result=result if isinstance(result, dict) else None,
                    error=None,
                    partial=bool((result or {}).get("partial")),
                )
        except asyncio.TimeoutError:
            await _push_event(unified_id, "error", "Scan timeout")
            if orch is None:
                async with _lock:
                    if unified_id in _jobs:
                        _jobs[unified_id]["completed_at"] = _time.time()
                        _jobs[unified_id]["error"] = "Scan timeout"
                await _set_job_state(unified_id, "FAILED", "Scan failed")
                await run_store.finalize_run(
                    unified_id,
                    status="failed",
                    result=None,
                    error="Scan timeout",
                    partial=False,
                )
                return
            partial_result = await orch.build_partial_result(
                "Scan timed out — showing partial results"
            )
            try:
                from backend.db.persistence import persist_pipeline_result

                _sid, delta_report, _rid = await persist_pipeline_result(
                    req.url,
                    partial_result,
                    orch._last_site_model,
                    orch._last_run_result,
                )
                if delta_report is not None:
                    partial_result["delta_report"] = delta_report
            except Exception:
                pass
            try:
                from backend.services.decision_insights import attach_decision_insights
                from backend.services.risk_explanation import attach_risk_explanation

                await attach_risk_explanation(partial_result)
                await attach_decision_insights(partial_result)
            except Exception:
                pass
            async with _lock:
                if unified_id in _jobs:
                    _jobs[unified_id]["completed_at"] = _time.time()
                    _jobs[unified_id]["error"] = "Scan timeout"
                    _jobs[unified_id]["result"] = partial_result
            if _resolve_pages_scanned(partial_result) == 0:
                async with _lock:
                    if unified_id in _jobs:
                        _jobs[unified_id]["error"] = "Scan timed out — no pages crawled"
                await _set_job_state(unified_id, "FAILED", "Scan failed: no pages were crawled")
                await run_store.finalize_run(
                    unified_id,
                    status="failed",
                    result=partial_result if isinstance(partial_result, dict) else None,
                    error="Scan timed out — no pages crawled",
                    partial=False,
                )
            else:
                await _set_job_state(unified_id, "PARTIAL", "Scan timed out — showing partial results")
                await run_store.finalize_run(
                    unified_id,
                    status="success",
                    result=partial_result if isinstance(partial_result, dict) else None,
                    error="Scan timeout",
                    partial=True,
                )
        except Exception as e:
            await _push_event(unified_id, "error", f"Scan failed: {e}")
            async with _lock:
                if unified_id in _jobs:
                    _jobs[unified_id]["completed_at"] = _time.time()
                    _jobs[unified_id]["error"] = str(e)
                    _jobs[unified_id]["result"] = None
            await _set_job_state(unified_id, "FAILED", "Scan failed")
            await run_store.finalize_run(
                unified_id,
                status="failed",
                result=None,
                error=str(e),
                partial=False,
            )
        finally:
            forced_failed = False
            async with _lock:
                job = _jobs.get(unified_id)
                if job and job.get("status") in {"QUEUED", "RUNNING"}:
                    job["completed_at"] = _time.time()
                    job["error"] = job.get("error") or "Scan ended unexpectedly"
                    forced_failed = True
            if forced_failed:
                await _set_job_state(unified_id, "FAILED", "Scan ended unexpectedly")
            async with _lock:
                status = (_jobs.get(unified_id) or {}).get("status")
            if status == "COMPLETE":
                await _push_event(unified_id, "success", "SCAN COMPLETE")
            elif status == "PARTIAL":
                await _push_event(unified_id, "detection", "Job completed with partial results")
            elif status == "FAILED":
                await _push_event(unified_id, "error", "Job failed")

            await _append_run_history(unified_id, req.url)

    asyncio.create_task(_run_job_bridge())

    return {
        "run_id": unified_id,
        "job_id": unified_id,
        "status": "started",
        "url": str(body.url).strip(),
    }


def _iso_from_ts(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _format_duration_human(start: float | None, end: float | None) -> str:
    if start is None or end is None:
        return "—"
    try:
        sec = max(0, int(round(float(end) - float(start))))
    except (TypeError, ValueError):
        return "—"
    m, s = divmod(sec, 60)
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _serialize_registry_run(rec: RunRecord) -> dict[str, Any]:
    uid = str(rec.run_id)
    risk = rec.risk_score
    try:
        risk_i = int(risk) if risk is not None else 0
    except (TypeError, ValueError):
        risk_i = 0
    st = str(rec.status)
    if st == "success":
        front_status = "completed"
    elif st == "failed":
        front_status = "failed"
    else:
        front_status = "running"
    summ = rec.summary or ""
    pages = 0
    issues = 0
    if "Pages:" in summ and "issues:" in summ:
        try:
            parts = summ.split(",")
            for p in parts:
                p = p.strip()
                if p.startswith("Pages:"):
                    pages = int(p.split(":")[1].strip())
                if p.startswith("issues:"):
                    issues = int(p.split(":")[1].strip())
        except Exception:
            pass
    return {
        "run_id": uid,
        "job_id": uid,
        "url": rec.target_url,
        "status": front_status,
        "risk_score": risk_i,
        "risk_level": "LOW RISK",
        "started_at": _iso_from_ts(rec.start_time),
        "completed_at": _iso_from_ts(rec.end_time),
        "duration": _format_duration_human(rec.start_time, rec.end_time),
        "pages": pages,
        "issues": issues,
    }


@app.get("/api/runs")
async def api_list_runs() -> list[dict[str, Any]]:
    """List runs from registry plus in-memory jobs (legacy job_* keys)."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    reg_list = await run_store.list_runs()
    reg_list.sort(key=lambda r: r.start_time, reverse=True)
    for rec in reg_list:
        rows.append(_serialize_registry_run(rec))
        seen.add(str(rec.run_id))

    async with _lock:
        snapshot = {k: dict(v) for k, v in _jobs.items()}

    for jid, job in snapshot.items():
        if jid in seen:
            continue
        if not str(jid).startswith("job_"):
            continue
        st = str(job.get("status") or "QUEUED")
        front = _run_status_to_frontend(st)
        res = job.get("result") if isinstance(job.get("result"), dict) else None
        pages, actions, issues = _bridge_compute_metrics(res)
        rs = 0
        if res:
            try:
                rs = int(res.get("risk_score") or 0)
            except (TypeError, ValueError):
                rs = 0
        target_url = str((res or {}).get("target_url") or "")
        rows.append(
            {
                "run_id": jid,
                "job_id": jid,
                "url": target_url,
                "status": front,
                "risk_score": rs,
                "risk_level": str((res or {}).get("risk_level") or "LOW RISK"),
                "started_at": _iso_from_ts(job.get("started_at")),
                "completed_at": _iso_from_ts(job.get("completed_at")),
                "duration": _format_duration_human(job.get("started_at"), job.get("completed_at")),
                "pages": pages,
                "issues": issues,
            }
        )

    def sort_key_iso(r: dict[str, Any]) -> str:
        return str(r.get("started_at") or "")

    rows.sort(key=sort_key_iso, reverse=True)
    return rows


def _build_run_detail_payload(run_key: str, job: dict[str, Any] | None, rec: RunRecord | None) -> dict[str, Any]:
    result = None
    if job and isinstance(job.get("result"), dict):
        result = dict(job["result"])
    elif rec:
        path = run_store.result_path(str(rec.run_id))
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    result = json.load(f)
            except Exception:
                result = None

    url = ""
    if isinstance(result, dict) and result.get("target_url"):
        url = str(result.get("target_url"))
    elif rec:
        url = rec.target_url
    elif job:
        url = ""

    status = "pending"
    if job:
        status = _run_status_to_frontend(str(job.get("status") or "QUEUED"))
    elif rec:
        status = "completed" if rec.status == "success" else ("failed" if rec.status == "failed" else "running")

    risk_score = 0
    risk_level = "LOW RISK"
    summary = {
        "total_pages_scanned": 0,
        "total_actions_run": 0,
        "total_issues_found": 0,
    }
    issues_out: list[dict[str, Any]] = []
    total_passed = 0
    total_failed = 0
    ux_score: int | None = None
    ux_label: str | None = None
    ux_color: str | None = None
    ux_summary: str | None = None
    top_improvements: list[Any] = []
    category_scores: dict[str, Any] = {}
    passed_checks: list[str] = []

    if isinstance(result, dict):
        try:
            risk_score = int(result.get("risk_score") or 0)
        except (TypeError, ValueError):
            risk_score = 0
        risk_level = str(result.get("risk_level") or "LOW RISK")
        try:
            if result.get("ux_score") is not None:
                ux_score = int(result.get("ux_score"))
        except (TypeError, ValueError):
            ux_score = None
        ux_label = result.get("ux_label") if isinstance(result.get("ux_label"), str) else None
        ux_color = result.get("ux_color") if isinstance(result.get("ux_color"), str) else None
        ux_summary = result.get("ux_summary") if isinstance(result.get("ux_summary"), str) else None
        _ti = result.get("top_improvements")
        if isinstance(_ti, list):
            top_improvements = list(_ti)
        _cs = result.get("category_scores")
        if isinstance(_cs, dict):
            category_scores = dict(_cs)
        _pc = result.get("passed_checks")
        if isinstance(_pc, list):
            passed_checks = [str(x) for x in _pc if x is not None]
        sm = result.get("summary") or {}
        if isinstance(sm, dict):
            summary = {
                "total_pages_scanned": int(sm.get("total_pages_scanned") or 0),
                "total_actions_run": int(sm.get("total_actions_run") or 0),
                "total_issues_found": int(sm.get("total_issues_found") or 0),
            }
        raw_issues = list(result.get("issues") or [])
        for it in raw_issues:
            if not isinstance(it, dict):
                continue
            row = dict(it)
            row.setdefault("severity", str(it.get("severity") or "medium").upper())
            row.setdefault(
                "type",
                str(it.get("type") or it.get("defect") or "Issue").replace("_", " ").title(),
            )
            row.setdefault(
                "page_url",
                str(it.get("page_url") or it.get("url") or it.get("page") or ""),
            )
            row.setdefault(
                "element",
                str(it.get("selector") or it.get("element") or ""),
            )
            row.setdefault(
                "description",
                str(it.get("message") or it.get("description") or ""),
            )
            row.setdefault(
                "user_message",
                str(it.get("user_message") or it.get("message") or ""),
            )
            row.setdefault(
                "improvement",
                str(it.get("improvement") or it.get("fix_suggestion") or ""),
            )
            ev = it.get("screenshot_path") or it.get("evidence")
            row.setdefault("evidence", ev)
            row.setdefault("screenshot_path", it.get("screenshot_path") or ev)
            issues_out.append(row)
        tr = result.get("test_results") or result.get("results")
        if isinstance(tr, list):
            total_passed = sum(1 for x in tr if isinstance(x, dict) and x.get("result") == "pass")
            total_failed = sum(1 for x in tr if isinstance(x, dict) and x.get("result") in ("fail", "error"))

    return {
        "run_id": run_key,
        "url": url,
        "status": status,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "ux_score": ux_score,
        "ux_label": ux_label,
        "ux_color": ux_color,
        "ux_summary": ux_summary,
        "top_improvements": top_improvements,
        "category_scores": category_scores,
        "passed_checks": passed_checks,
        "summary": summary,
        "issues": issues_out,
        "results": {
            "total": total_passed + total_failed,
            "passed": total_passed,
            "failed": total_failed,
        },
    }


@app.get("/api/runs/{run_key}")
async def api_get_run(run_key: str) -> dict[str, Any]:
    """Single run detail; run_key may be run_* or legacy job_*."""
    async with _lock:
        job = _jobs.get(run_key)
    rec = await run_store.get_run(run_key)
    if not job and not rec:
        raise HTTPException(status_code=404, detail="run not found")
    return _build_run_detail_payload(run_key, job, rec)


@app.get("/api/runs/{run_key}/status")
async def api_run_status(run_key: str) -> dict[str, Any]:
    """Polling status for live preview."""
    async with _lock:
        exists = run_key in _jobs
    rec = await run_store.get_run(run_key)
    if not exists and not rec:
        raise HTTPException(status_code=404, detail="run not found")
    if exists:
        payload = await _bridge_run_status_payload(run_key)
        payload["run_id"] = run_key
        return payload
    rec2 = await run_store.get_run(run_key)
    if rec2 and rec2.end_time is not None:
        path = run_store.result_path(run_key)
        result = None
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    result = json.load(f)
            except Exception:
                result = None
        pages, actions, issues = _bridge_compute_metrics(result if isinstance(result, dict) else None)
        rs = None
        rl = None
        if isinstance(result, dict):
            try:
                rs = int(result.get("risk_score") or 0)
            except (TypeError, ValueError):
                rs = None
            rl = str(result.get("risk_level") or "") or None
        return {
            "run_id": run_key,
            "status": "completed" if rec2.status == "success" else "failed",
            "stage": "done",
            "progress": 100,
            "current_action": "",
            "pages_found": pages,
            "actions_run": actions,
            "issues_found": issues,
            "elapsed_seconds": int(max(0.0, float(rec2.end_time) - float(rec2.start_time))),
            "risk_score": rs,
            "risk_level": rl,
        }
    raise HTTPException(status_code=404, detail="run not found")


@app.get("/api/runs/{run_key}/logs")
async def api_run_logs(run_key: str) -> dict[str, Any]:
    """Merged logs from logs.txt and console_logs.txt."""
    rec = await run_store.get_run(run_key)
    async with _lock:
        in_mem = run_key in _jobs
    if not rec and not in_mem:
        raise HTTPException(status_code=404, detail="run not found")
    lines = _merge_run_log_lines(run_key)
    return {"run_id": run_key, "logs": lines, "log_count": len(lines)}


@app.get("/api/runs/{run_key}/stream")
async def api_run_stream(run_key: str) -> StreamingResponse:
    """SSE: job events + merged log files + periodic metrics."""

    async def event_generator():
        yield f"data: {_json.dumps({'type': 'connected', 'run_id': run_key})}\n\n".encode(
            "utf-8"
        )
        rec_done = await run_store.get_run(run_key)
        async with _lock:
            job0 = _jobs.get(run_key)
        if not job0 and rec_done and rec_done.end_time is not None:
            path = run_store.result_path(run_key)
            result: dict[str, Any] = {}
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        result = json.load(f)
                except Exception:
                    result = {}
            try:
                rs = int(result.get("risk_score") or 0)
            except (TypeError, ValueError):
                rs = 0
            rl = str(result.get("risk_level") or "LOW RISK")
            done = {
                "type": "complete",
                "risk_score": rs,
                "risk_level": rl,
                "run_id": run_key,
            }
            yield f"data: {_json.dumps(done)}\n\n".encode("utf-8")
            return

        last_log_count = 0
        last_event_idx = 0
        t0 = _time.monotonic()
        last_metric = 0.0
        while _time.monotonic() - t0 < 600.0:
            await asyncio.sleep(0.5)

            lines = _merge_run_log_lines(run_key)
            if len(lines) > last_log_count:
                new_lines = lines[last_log_count:]
                last_log_count = len(lines)
                for ln in new_lines:
                    stg = _infer_stage_from_message(ln)
                    ts = _time.strftime("%H:%M:%S")
                    ev = {
                        "type": "log",
                        "stage": stg,
                        "message": ln,
                        "timestamp": ts,
                    }
                    yield f"data: {_json.dumps(ev)}\n\n".encode("utf-8")

            async with _lock:
                evs = list(_jobs_events.get(run_key, []))
                job = dict(_jobs.get(run_key) or {})
            if len(evs) > last_event_idx:
                for e in evs[last_event_idx:]:
                    msg = str(e.get("message") or "")
                    stg = _infer_stage_from_message(msg)
                    ts = _time.strftime("%H:%M:%S")
                    ev = {
                        "type": "log",
                        "stage": stg,
                        "message": msg,
                        "timestamp": ts,
                    }
                    yield f"data: {_json.dumps(ev)}\n\n".encode("utf-8")
                last_event_idx = len(evs)

            now = _time.monotonic()
            if now - last_metric >= 2.0:
                last_metric = now
                status_payload = await _bridge_run_status_payload(run_key)
                metric = {
                    "type": "metric",
                    "pages_found": status_payload.get("pages_found", 0),
                    "actions_run": status_payload.get("actions_run", 0),
                    "issues_found": status_payload.get("issues_found", 0),
                    "stage": status_payload.get("stage", "execute"),
                    "progress": status_payload.get("progress", 0),
                }
                yield f"data: {_json.dumps(metric)}\n\n".encode("utf-8")
                sc = {
                    "type": "stage_change",
                    "stage": str(status_payload.get("stage") or "execute"),
                }
                yield f"data: {_json.dumps(sc)}\n\n".encode("utf-8")

            st = str(job.get("status") or "")
            if st in ("COMPLETE", "PARTIAL"):
                res = job.get("result") if isinstance(job.get("result"), dict) else {}
                rs = int(res.get("risk_score") or 0) if res else 0
                rl = str(res.get("risk_level") or "LOW RISK")
                done = {
                    "type": "complete",
                    "risk_score": rs,
                    "risk_level": rl,
                    "run_id": run_key,
                }
                yield f"data: {_json.dumps(done)}\n\n".encode("utf-8")
                return
            if st == "FAILED":
                err = {
                    "type": "error",
                    "message": str(job.get("error") or job.get("status_message") or "Run failed"),
                }
                yield f"data: {_json.dumps(err)}\n\n".encode("utf-8")
                return

        yield f"data: {_json.dumps({'type': 'timeout', 'message': 'Stream timeout'})}\n\n".encode(
            "utf-8"
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/modules")
async def api_modules() -> dict[str, Any]:
    """Modules derived from legacy flow ids (TASK_GROUPS entries are presets, not listed as modules)."""
    preset_ids = set(TASK_GROUPS.keys())
    mods: list[dict[str, Any]] = []
    for fid in sorted(LEGACY_FLOW_TO_TASKS.keys()):
        tasks = LEGACY_FLOW_TO_TASKS.get(fid) or []
        mods.append(
            {
                "id": fid,
                "name": fid.replace("_", " ").title(),
                "description": f"Covers flows: {', '.join(tasks)}" if tasks else "Legacy flow bundle",
                "enabled": True,
                "test_count": max(1, len(tasks) * 2),
                "status": "available",
            }
        )
    return {"modules": mods, "total": len(mods), "presets": sorted(preset_ids)}


@app.post("/api/runs/{run_key}/rerun")
async def api_rerun(run_key: str) -> dict[str, Any]:
    """Rerun using saved api_run_config.json for that run."""
    path = run_store.run_dir(run_key) / "api_run_config.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Original run config not found")
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    body = ApiRunBody(**raw)
    out = await api_run(body)
    return {"run_id": out["run_id"], "status": "started", "job_id": out["job_id"]}


@app.get("/api/runs/{run_key}/compare")
async def api_run_compare(run_key: str) -> dict[str, Any]:
    """Compare this run's result.json to the previous run on disk."""
    from backend.baseline_comparator import compare_disk_runs

    return compare_disk_runs(Path("runs"), run_key)


# ═══════════════════════════════════════════
# SCREENSHOT ENDPOINTS (Nischay)
# Note: ``/runs`` is not mounted as StaticFiles here because it would
# shadow the existing GET /runs/history route. Use these API URLs instead.
# ═══════════════════════════════════════════

from fastapi.responses import FileResponse as _ScreenshotFileResponse


def _safe_screenshot_filename(filename: str) -> str:
    fn = (filename or "").strip()
    if not fn or ".." in fn or "/" in fn or "\\" in fn:
        raise HTTPException(status_code=400, detail="invalid filename")
    return Path(fn).name


@app.get("/api/runs/{run_id}/screenshots", tags=["screenshots"])
async def get_run_screenshots(run_id: str) -> dict[str, Any]:
    """List screenshot metadata (index.json) for a run."""
    screenshots_dir = Path("runs") / run_id / "screenshots"
    index_path = screenshots_dir / "index.json"
    if not index_path.is_file():
        return {"run_id": run_id, "screenshots": [], "count": 0}
    try:
        with open(index_path, encoding="utf-8") as f:
            screenshots = json.load(f)
        if not isinstance(screenshots, list):
            screenshots = []
        return {"run_id": run_id, "screenshots": screenshots, "count": len(screenshots)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/runs/{run_id}/screenshots/{filename}", tags=["screenshots"])
async def get_screenshot_file(run_id: str, filename: str) -> _ScreenshotFileResponse:
    """Serve a PNG captured during the run."""
    safe_fn = _safe_screenshot_filename(filename)
    filepath = Path("runs") / run_id / "screenshots" / safe_fn
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return _ScreenshotFileResponse(
        path=str(filepath),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )

