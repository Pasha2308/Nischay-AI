/*
═══════════════════════════════════════════════
NISCHAY AI — BACKEND AUDIT
═══════════════════════════════════════════════

ENDPOINTS FOUND (api/server.py):
  POST /jobs/test.run -> TestRunResponse
    - returns: { status: "started", job_id: string, message, scan_mode: "fast"|"deep", scan_task: string }
    - NOTE: This is the existing “start run” endpoint (job-based).

  GET /report/{report_id} -> ShareableReportResponse
    - returns: { report_id: string, summary: any, issues: any[], risk_score: number|null, delta: object|null }

  POST /synthetic/generate -> dict
    - returns: { domain: string, count: number, rows: object[] }

  GET /dashboard/summary -> dict
    - returns: { total_runs: number, last_decision: string|null, last_job_id: string|null, pass_count: number, fail_count: number }

  GET /runs/history -> dict
    - returns: { runs: Array<{ job_id: string, url: string, decision: string, completed_at: number, status: string }> }

  GET /results -> ResultsResponse
    - returns: { job_id: string|null, status: string, started_at: number|null, completed_at: number|null, result: object|null, error: string|null, scan_mode, scan_task }

  GET /results/{job_id} -> ResultsResponse
    - returns: same shape as /results

  GET /jobs/{job_id}/status -> JobStatusResponse
    - returns: { job_id: string, status: string, message: string, progress: number }

  GET /jobs/{job_id}/events -> dict
    - returns: { job_id: string, events: Array<{ time: number, type: string, message: string, name?: string, payload?: object }> }

  GET /healthz -> dict
    - returns: { status: "ok" }

ENDPOINTS FOUND (api/run_store.py-driven “runs” API support used elsewhere in repo):
  NOTE: `api/run_store.py` implements on-disk run registry + artifacts under `runs/`.
  Any `/api/runs*` endpoints are NOT present in `api/server.py` as of this audit (they must be appended if needed).

RUN ID FIELD NAME:
  - Canonical “run id” in artifacts/registry is **run_id** (see `RunRecord.run_id` in `shared/models/run_record.py`).
  - The existing start endpoint returns **job_id** (TestRunResponse.job_id) — job-based API.
  - Executor/orchestrator generate run ids like `run_<8 hex>` in multiple places (e.g. `backend/executor/executor.py`, `backend/scheduler.py`).

RUN RESULT STORAGE (on disk):
  - Registry: `runs/registry.json`
    - contains: { version: 1, runs: RunRecord[] }
  - Per-run directory: `runs/<run_id>/`
  - Result JSON (structured API payload): `runs/<run_id>/result.json` (written by `api/run_store.py` via `result_path(run_id)`)
  - Execution trace JSON: `runs/<run_id>/execution_trace.json` (written by `backend/run_artifacts.py`)
  - Metadata: `runs/<run_id>/metadata.json` (written by `backend/run_artifacts.py` and mirrored by `api/run_store.finalize_run`)

LOG STORAGE (on disk):
  - Primary run log (run_store): `runs/<run_id>/logs.txt` (written by `api/run_store.py` via `logs_path(run_id)`)
  - Console logs artifact: `runs/<run_id>/console_logs.txt` (written by `backend/run_artifacts.py`)

RUN STATUS VALUES (exact strings found):
  - api/server.py job statuses (in-memory jobs):
    - "QUEUED" | "RUNNING" | "WAITING_FOR_LOGIN" | "SCANNING" | "PARTIAL" | "COMPLETE" | "FAILED"
  - shared/models/run_record.py run statuses (registry /api/runs world):
    - "running" | "success" | "failed"

STREAMING SUPPORT:
  - Existing streaming-like support: **YES (polling)** via `GET /jobs/{job_id}/events` (returns accumulated events array; not SSE).
  - Dedicated SSE endpoint: **NO** in current `api/server.py`.
  - Dedicated `/api/runs/{run_id}/status`: **NO** in current `api/server.py`.

MODULES IMPLEMENTED (backend reality; stable IDs you can surface in UI):
  - Micro-task IDs (TASK_REGISTRY keys in `backend/core/task_registry.py`):
    - login_user
    - search_product
    - open_product_from_search
    - add_to_cart
    - apply_coupon
    - start_checkout
    - fill_address_form
    - place_order_attempt
    - contact_support
    - check_page_load
    - check_navigation_links

  - Task bundles / presets (TASK_GROUPS):
    - quick_scan
    - conversion_scan
    - auth_scan
    - full_app_scan

  - Legacy “flow” aliases supported (LEGACY_FLOW_TO_TASKS):
    - auth, browse, cart, checkout, support, ui, product, navigation, search, coupon

GAPS TO FIX (for the frontend contract in this prompt):
  1. Frontend expects `/api/run`, `/api/runs`, `/api/runs/{id}`, `/api/runs/{id}/status`, `/api/runs/{id}/logs`, `/api/runs/{id}/stream`, `/api/modules` — these do NOT exist in `api/server.py` today.
  2. Backend run artifacts currently split logs into `logs.txt` (run_store) and `console_logs.txt` (run_artifacts); frontend live preview needs one authoritative stream source.
  3. Backend has job progress + events, but not SSE; frontend live preview requires SSE or a polling fallback built around run_id-based endpoints.
  4. API start response shape mismatch: existing start endpoint returns `job_id`, while the new frontend contract expects `run_id`.

═══════════════════════════════════════════════
*/

