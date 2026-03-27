"""HTTP API for triggering QA runs."""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from typing import Any, Optional

# Windows Playwright reliability: use Proactor event loop policy.
if sys.platform.startswith("win") and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared.models.config import FrameworkConfig


# App must be defined before middleware is applied.
app = FastAPI(title="Reqon AI API", version="0.1.0")

# CORS for local dev / demo (frontend on a different port).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthPayload(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TestRunRequest(BaseModel):
    url: str = Field(..., min_length=1)
    auth: Optional[AuthPayload] = None


class TestRunResponse(BaseModel):
    status: str = "started"
    job_id: str
    message: str = "Scan started"


class ResultsResponse(BaseModel):
    job_id: Optional[str] = None
    status: str
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    message: str
    progress: int


class SyntheticGenerateRequest(BaseModel):
    domain: str = Field(..., description="ecommerce | healthcare | finance | auth")
    count: int = Field(10, ge=1, le=1000)


def _build_failed_result(error_message: str, defect: str = "runtime_error") -> dict[str, Any]:
    return {
        "summary": {
            "total_pages_scanned": 0,
            "total_actions_run": 0,
            "total_issues_found": 1,
        },
        "risk_score": 100,
        "risk_level": "LOW RISK",
        "issues_by_severity": {
            "critical": [
                {
                    "type": "error",
                    "defect": defect,
                    "severity": "critical",
                    "message": error_message,
                }
            ],
            "high": [],
            "medium": [],
            "low": [],
        },
        "issues": [
            {
                "type": "error",
                "defect": defect,
                "severity": "critical",
                "message": error_message,
            }
        ],
        "pages": [],
        "actions_run": [],
        "console_errors": [],
        "failed_actions": [],
        "missing_elements": [],
        "mode": "failed_runtime",
    }


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


async def _set_job_state(job_id: str, status: str, message: str) -> None:
    async with _lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = status
            _jobs[job_id]["status_message"] = message
            _jobs[job_id]["progress"] = _STATUS_PROGRESS.get(status, 0)

try:
    from anthropic import AsyncAnthropic
except Exception:
    AsyncAnthropic = None  # type: ignore[assignment]


def _fallback_executive_summary(risk_level: str, issues: list[dict[str, Any]]) -> str:
    top = issues[0]["message"] if issues else "No major issues were detected."
    return (
        f"Overall risk is {risk_level}. "
        f"The biggest issue observed is: {top} "
        "Recommended action: prioritize fixing the top issue first, then rerun the scan to verify risk reduction."
    )


def _extract_text_from_anthropic_response(resp: Any) -> str:
    parts: list[str] = []
    for block in getattr(resp, "content", []) or []:
        txt = getattr(block, "text", None)
        if txt:
            parts.append(txt)
    return " ".join(parts).strip()


def _build_executive_prompt(risk_level: str, risk_score: int, issues: list[dict[str, Any]]) -> str:
    top_issue = issues[0] if issues else {"message": "No issues found", "severity": "low", "defect": "none"}
    return (
        "You are a QA risk analyst. Write a 3-sentence summary explaining:\n"
        "- overall risk level\n"
        "- biggest issue\n"
        "- recommended action\n\n"
        f"Risk level: {risk_level}\n"
        f"Risk score: {risk_score}\n"
        f"Top issue severity: {top_issue.get('severity')}\n"
        f"Top issue defect: {top_issue.get('defect')}\n"
        f"Top issue message: {top_issue.get('message')}\n"
    )


async def _generate_executive_summary(job_id: str) -> None:
    async with _lock:
        job = _jobs.get(job_id)
        result = (job or {}).get("result") if job else None
        if not isinstance(result, dict):
            return
        issues = list(result.get("issues") or [])
        risk_score = int(result.get("risk_score") or 0)
        risk_level = str(result.get("risk_level") or "LOW RISK")

    if AsyncAnthropic is None or not os.environ.get("ANTHROPIC_API_KEY"):
        summary = _fallback_executive_summary(risk_level, issues)
    else:
        try:
            client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            prompt = _build_executive_prompt(risk_level, risk_score, issues)
            resp = await client.messages.create(
                model="claude-3-5-haiku-latest",
                max_tokens=220,
                temperature=0.2,
                system="You produce concise executive QA risk summaries.",
                messages=[{"role": "user", "content": prompt}],
            )
            summary = _extract_text_from_anthropic_response(resp) or _fallback_executive_summary(
                risk_level, issues
            )
        except Exception:
            summary = _fallback_executive_summary(risk_level, issues)

    async with _lock:
        if job_id in _jobs and isinstance(_jobs[job_id].get("result"), dict):
            _jobs[job_id]["result"]["executive_summary"] = summary


async def _push_event(job_id: str, event_type: str, message: str) -> None:
    async with _lock:
        if job_id not in _jobs_events:
            _jobs_events[job_id] = []
        _jobs_events[job_id].append(
            {
                "time": time.time(),
                "type": event_type,
                "message": message,
            }
        )


async def _emit_scan_progress(job_id: str, pipeline_task: "asyncio.Task[dict[str, Any]]") -> None:
    steps = [
        "Checking page performance...",
        "Scanning for console errors...",
        "Detecting interactive elements...",
        "Testing form interactions...",
        "Checking for missing elements...",
        "Crawling linked pages...",
        "Calculating risk score...",
    ]
    for step in steps:
        if pipeline_task.done():
            return
        await _push_event(job_id, "action", step)
        await asyncio.sleep(1.2)

_DEMO_RESULT: dict[str, Any] = {
    "summary": {
        "total_pages_scanned": 3,
        "total_actions_run": 4,
        "total_issues_found": 3,
    },
    "risk_score": 210,
    "risk_level": "HIGH RISK",
    "issues_by_severity": {
        "critical": [
            {
                "type": "assertion_failure",
                "defect": "page_load_failure",
                "severity": "critical",
                "message": "Page appears blank (no title, no body text)",
                "test_id": "deterministic_smoke",
            }
        ],
        "high": [
            {
                "type": "console_error",
                "defect": "console_error",
                "severity": "high",
                "message": "[error] TypeError: Cannot read properties of undefined",
                "test_id": "deterministic_smoke",
            }
        ],
        "medium": [
            {
                "type": "failed_action",
                "defect": "missing_element",
                "severity": "medium",
                "message": "Timeout 10000ms exceeded while waiting for selector \"button:visible\"",
                "test_id": "deterministic_smoke",
                "phase": "step",
                "step_index": 2,
                "action_type": "click",
                "selector": "button:visible",
            }
        ],
        "low": [],
    },
    "issues": [
        {
            "type": "assertion_failure",
            "defect": "page_load_failure",
            "severity": "critical",
            "message": "Page appears blank (no title, no body text)",
            "test_id": "deterministic_smoke",
        },
        {
            "type": "console_error",
            "defect": "console_error",
            "severity": "high",
            "message": "[error] TypeError: Cannot read properties of undefined",
            "test_id": "deterministic_smoke",
        },
        {
            "type": "failed_action",
            "defect": "missing_element",
            "severity": "medium",
            "message": "Timeout 10000ms exceeded while waiting for selector \"button:visible\"",
            "test_id": "deterministic_smoke",
            "phase": "step",
            "step_index": 2,
            "action_type": "click",
            "selector": "button:visible",
        },
    ],
    "pages": [
        {"page_id": "page_demo_1", "url": "https://example.com", "title": "Home", "page_type": "static"},
        {"page_id": "page_demo_2", "url": "https://example.com/login", "title": "Login", "page_type": "form"},
        {"page_id": "page_demo_3", "url": "https://example.com/profile", "title": "Profile", "page_type": "detail"},
    ],
    "actions_run": [
        {"test_id": "deterministic_smoke", "phase": "step", "step_index": 0, "action_type": "navigate", "status": "pass"},
        {"test_id": "deterministic_smoke", "phase": "step", "step_index": 1, "action_type": "wait", "status": "pass"},
        {"test_id": "deterministic_smoke", "phase": "step", "step_index": 2, "action_type": "click", "status": "fail"},
        {"test_id": "deterministic_smoke", "phase": "step", "step_index": 3, "action_type": "fill", "status": "pass"},
    ],
    "console_errors": ["[error] TypeError: Cannot read properties of undefined"],
    "failed_actions": [
        {
            "test_id": "deterministic_smoke",
            "phase": "step",
            "step_index": 2,
            "action_type": "click",
            "selector": "button:visible",
            "error_message": "Timeout 10000ms exceeded while waiting for selector \"button:visible\"",
        }
    ],
    "missing_elements": [
        {
            "test_id": "deterministic_smoke",
            "phase": "step",
            "step_index": 2,
            "action_type": "click",
            "selector": "button:visible",
            "message": "Timeout 10000ms exceeded while waiting for selector \"button:visible\"",
        }
    ],
    "run_id": "run_demo_0001",
    "duration": 2.4,
    "mode": "demo_preloaded",
    "executive_summary": (
        "Overall risk is HIGH RISK due to concentrated critical and high-severity defects. "
        "The biggest issue is a page-load failure path that can block key user flows. "
        "Recommended action: fix load blockers first, then address console/runtime errors and re-scan."
    ),
}


@app.post("/jobs/test.run", response_model=TestRunResponse)
async def trigger_test_run(req: TestRunRequest) -> Any:
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

            config = FrameworkConfig(target_url=req.url)
            if req.auth and req.auth.username and req.auth.password:
                await _set_job_state(
                    job_id,
                    "WAITING_FOR_LOGIN",
                    "Please login in the Chrome window",
                )
                config.auth = {
                    "login_url": req.url,
                    "username": req.auth.username,
                    "password": req.auth.password,
                    "auto_detect": True,
                }
                await _push_event(job_id, "detection", "Login page detected")
                await _push_event(job_id, "action", "⏸ Waiting for you to login in the browser window...")
            orch = Orchestrator(config)

            # Guard against stalled pipelines.
            pipeline_task = asyncio.create_task(asyncio.wait_for(orch._run_pipeline(), timeout=120))
            progress_task = asyncio.create_task(_emit_scan_progress(job_id, pipeline_task))
            result = await pipeline_task
            if not progress_task.done():
                progress_task.cancel()
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
            # Non-blocking executive summary generation.
            asyncio.create_task(_generate_executive_summary(job_id))
        except asyncio.TimeoutError:
            await _push_event(job_id, "error", "Scan timeout")
            partial_result = orch.build_partial_result("Scan timed out — showing partial results")
            async with _lock:
                if job_id in _jobs:
                    _jobs[job_id]["completed_at"] = time.time()
                    _jobs[job_id]["error"] = "Scan timeout"
                    _jobs[job_id]["result"] = partial_result
            await _set_job_state(job_id, "PARTIAL", "Scan timed out — showing partial results")
        except Exception as e:
            await _push_event(job_id, "error", f"Scan failed: {e}")
            async with _lock:
                if job_id in _jobs:
                    _jobs[job_id]["completed_at"] = time.time()
                    _jobs[job_id]["error"] = str(e)
                    _jobs[job_id]["result"] = _build_failed_result(str(e))
            await _set_job_state(job_id, "FAILED", "Scan failed")
        finally:
            # Never leave a job in pending/running forever.
            forced_failed = False
            async with _lock:
                job = _jobs.get(job_id)
                if job and job.get("status") in {"QUEUED", "RUNNING"}:
                    job["completed_at"] = time.time()
                    job["error"] = job.get("error") or "Scan ended unexpectedly"
                    job["result"] = job.get("result") or _build_failed_result(
                        str(job["error"]),
                        defect="unexpected_termination",
                    )
                    forced_failed = True
            if forced_failed:
                await _set_job_state(job_id, "FAILED", "Scan ended unexpectedly")
            async with _lock:
                status = (_jobs.get(job_id) or {}).get("status")
            if status == "COMPLETE":
                await _push_event(job_id, "success", "Job completed")
            elif status == "PARTIAL":
                await _push_event(job_id, "detection", "Job completed with partial results")
            elif status == "FAILED":
                await _push_event(job_id, "error", "Job failed")

    asyncio.create_task(_run_job())

    return TestRunResponse(job_id=job_id)


@app.get("/demo")
async def demo() -> dict[str, Any]:
    """Instant demo payload for presentations (no waiting)."""
    return _DEMO_RESULT


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

