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

def _normalize_scan_task(raw: str | None) -> str:
    st = (raw or "full_app").strip().lower()
    if st in ("full_app", "auth", "checkout", "forms"):
        return st
    return "full_app"


def _executive_summary_system_prompt(scan_task: str | None) -> str:
    """Task-aware system prompt for executive summary (exactly three sentences)."""
    st = _normalize_scan_task(scan_task)
    core = (
        "You write an executive scan summary for stakeholders. "
        "Output exactly three sentences total, in plain text only (no headings, bullets, markdown, or extra lines). "
        "Use only the facts provided in the user message; do not invent URLs, page counts, or defect counts. "
        "You must explicitly include all of: pages scanned, number of issues found, the most critical issue and its page, "
        "business impact, and a recommended fix — using the three-line structure supplied verbatim in the user message. "
        "Do not use stock phrases (e.g. 'it is important to', 'robust', 'leverage', 'holistic', "
        "'in today's landscape', 'moving forward', 'delve', 'synergy', 'paradigm').\n\n"
    )
    focus = {
        "full_app": (
            "Task context: FULL APP — describe overall breadth of coverage and site health implied by the facts.\n"
        ),
        "auth": (
            "Task context: AUTH — when facts support it, tie the top issue to sign-in, session, or access-control risk.\n"
        ),
        "checkout": (
            "Task context: CHECKOUT — when facts support it, tie the top issue to cart, payment, or purchase flow risk.\n"
        ),
        "forms": (
            "Task context: FORMS — when facts support it, tie the top issue to form validation, submission, or input risk.\n"
        ),
    }
    return core + focus[st]


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
    """top_issue, page, business_impact, fix for the executive summary template."""
    top = _top_issues_for_summary(issues, 1)
    if not top:
        return (
            "no issues detected",
            url,
            "no material impact identified from automated findings",
            "No remediation required from this scan",
        )
    iss = top[0]
    top_issue = str(iss.get("message") or iss.get("type") or "issue")[:500]
    page = str(iss.get("page_url") or "").strip() or url
    business_impact = str(iss.get("business_impact") or "").strip() or "product quality and user trust"
    fix = str(iss.get("fix_suggestion") or "").strip() or "Review and remediate the reported defect"
    return (top_issue, page, business_impact, fix)


def _render_executive_summary(
    url: str, pages_scanned: int, total_defects: int, issues: list[dict[str, Any]]
) -> str:
    top_issue, page, business_impact, fix = _executive_summary_template_fields(issues, url)
    return (
        f"{url} scan covered {pages_scanned} pages and found {total_defects} issues.\n"
        f"The most critical issue is {top_issue} on {page}.\n"
        f"This impacts {business_impact}. Recommended action: {fix}."
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
    lines: list[str] = [
        f"Scan task: {st}.",
        "",
        "Produce exactly three sentences using this exact three-line structure (same line breaks, same facts):",
        "",
        f"{url} scan covered {pages} pages and found {n_def} issues.",
        f"The most critical issue is {top_issue} on {page}.",
        f"This impacts {bi}. Recommended action: {fix}.",
        "",
        "Placeholder meanings (do not contradict these numbers or URLs):",
        f"- pages scanned: {pages}",
        f"- issues (defects) count: {n_def}",
        f"- top_issue text: {top_issue}",
        f"- page: {page}",
        f"- business_impact: {bi}",
        f"- recommended fix: {fix}",
        "",
        f"Severity breakdown: critical={sev['critical']}, high={sev['high']}, "
        f"medium={sev['medium']}, low={sev['low']}; "
        f"distinct business_impact tags: {', '.join(impact_tags) if impact_tags else '(none)'}",
        f"Trend / delta (if relevant): {_trend_context(result)}",
    ]
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
            config = FrameworkConfig(
                target_url=req.url,
                scan_mode=sm,
                scan_task=st,
                flows=flow_list,
                task_type=tt,
                micro_task=mt,
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

