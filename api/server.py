"""HTTP API for triggering QA runs."""

from __future__ import annotations

import asyncio
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


class TestRunRequest(BaseModel):
    url: str = Field(..., min_length=1)


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


# ---------------------------------------------------------------------
# In-memory job/result storage (simple, no DB)
# ---------------------------------------------------------------------
_jobs: dict[str, dict[str, Any]] = {}
_latest_job_id: str | None = None
_lock = asyncio.Lock()

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
            "status": "started",
            "started_at": started_at,
            "completed_at": None,
            "result": None,
            "error": None,
        }
        _latest_job_id = job_id

    # Lazy import so the API can start even if Playwright isn't installed yet.
    from backend.orchestrator import Orchestrator

    config = FrameworkConfig(target_url=req.url)
    orch = Orchestrator(config)

    async def _run_job() -> None:
        try:
            # Orchestrator has an async pipeline method; use it directly.
            result = await orch._run_pipeline()
            async with _lock:
                _jobs[job_id]["status"] = "completed"
                _jobs[job_id]["completed_at"] = time.time()
                _jobs[job_id]["result"] = result
        except Exception as e:
            async with _lock:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["completed_at"] = time.time()
                _jobs[job_id]["error"] = str(e)
                _jobs[job_id]["result"] = {
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
                                "defect": "runtime_error",
                                "severity": "critical",
                                "message": str(e),
                            }
                        ],
                        "high": [],
                        "medium": [],
                        "low": [],
                    },
                    "issues": [
                        {
                            "type": "error",
                            "defect": "runtime_error",
                            "severity": "critical",
                            "message": str(e),
                        }
                    ],
                    "pages": [],
                    "actions_run": [],
                    "console_errors": [],
                    "failed_actions": [],
                    "missing_elements": [],
                    "mode": "failed_runtime",
                }

    asyncio.create_task(_run_job())

    return TestRunResponse(job_id=job_id)


@app.get("/demo")
async def demo() -> dict[str, Any]:
    """Instant demo payload for presentations (no waiting)."""
    return _DEMO_RESULT


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
            status=data.get("status", "unknown"),
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
            status=data.get("status", "unknown"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
        )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}

