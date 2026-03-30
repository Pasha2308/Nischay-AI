# Nischay AI 🛡️

> Autonomous QA Intelligence Platform for E-Commerce

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Status](https://img.shields.io/badge/status-MVP-green)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![React](https://img.shields.io/badge/react-18-cyan)

---

## What is Nischay AI?

Nischay AI is an autonomous QA system for e-commerce sites: it drives a real browser (Playwright), runs scripted commerce flows and checks, aggregates defects and console/network signals, and produces structured results with UX-oriented scoring and reporting. It is aimed at teams that need repeatable smoke and conversion-path validation without maintaining large manual test suites.

**Core loop:**

URL → Crawl (optional) → Plan → Execute → Detect → Score → Report

---

## Features

Features present in this repository:

- **HTTP API (FastAPI)** — Trigger test runs, poll job status, stream events, fetch results, health checks, dashboard summary, shareable reports, synthetic data generation, and a **Nischay AI frontend bridge** (`/api/run`, `/api/runs`, logs, SSE stream, modules, rerun, compare, screenshots).
- **Orchestrated pipeline** — `Orchestrator` coordinates optional crawl, deterministic test planning, and Playwright-based execution (`backend/orchestrator.py`).
- **Optional website crawling** — Discovery and page modeling (`backend/crawler/`), configurable via framework config.
- **Deterministic & planner paths** — `build_deterministic_smoke_plan`, schema-validated plans (`backend/planner/`, `backend/deterministic_plan.py`).
- **E-commerce micro-tasks** — Registered tasks such as search, add to cart, checkout steps, login, coupons, support contact (`backend/core/micro_tasks.py`, `TASK_REGISTRY` in `backend/core/task_registry.py`).
- **Tool-based executor** — Actions via navigation, forms, extraction, assertions, screenshot evidence (`backend/executor/`).
- **Structured run output** — Issues, summaries, actions trace, console/network signals (`backend/structured_run_output.py`).
- **UX scoring engine** — User-experience-focused scores and labels from issue payloads (`backend/ux_scorer.py`), integrated into structured output.
- **Screenshot capture** — Run-scoped screenshots under `runs/<run_id>/screenshots/` (`backend/screenshot_manager.py`, wired from orchestrator).
- **Defect intelligence & reporting** — Enrichment hooks, HTML/JSON reports, regression hints (`backend/services/defect_intelligence.py`, `backend/reporter/`).
- **Run persistence** — Registry and per-run artifacts (`api/run_store.py`, `runs/`, `backend/run_artifacts.py`).
- **Baseline comparison** — Compare runs on disk (`backend/baseline_comparator.py`).
- **Optional LLM integration** — OpenAI-compatible client for explanations and insights when API keys are configured (`backend/services/llm_client.py`, `backend/ai_explainer.py`).
- **Optional PostgreSQL** — Async SQLAlchemy models and session helpers (`backend/db/`).
- **Coverage & visual baselines** — Registry utilities under `shared/utils/coverage/`.
- **React + Vite frontend** — Dashboard, new test, live preview, modules, results (route still available), history, issues, analytics, schedules, alerts, integrations, settings (`frontend/src/App.jsx`).

---

## Architecture

### High-Level Flow

```
┌─────────────┐     ┌───────────┐     ┌─────────────┐     ┌──────────────┐
│  FastAPI    │────▶│Orchestrator│────▶│ Playwright  │────▶│ Structured   │
│  api/server │     │  pipeline  │     │  + tasks    │     │ output + UX  │
└─────────────┘     └───────────┘     └─────────────┘     └──────┬───────┘
       │                    │                   │                   │
       │                    ▼                   ▼                   ▼
       │             ┌───────────┐     ┌─────────────┐     ┌──────────────┐
       │             │  Crawler  │     │ Micro-tasks │     │ runs/ + JSON │
       │             │ (optional)│     │ / executor  │     │ reports      │
       │             └───────────┘     └─────────────┘     └──────────────┘
       │
       ▼
┌──────────────┐
│ React (Vite) │
└──────────────┘
```

### Project Structure

```
Feuji/   (repository root; name may vary)
├── api/
│   ├── server.py              # FastAPI app: jobs, reports, dashboard, Nischay bridge, screenshots
│   └── run_store.py           # Run registry, result.json, logs under runs/
├── backend/
│   ├── orchestrator.py        # Crawl → plan → execute pipeline
│   ├── structured_run_output.py  # Issues, risk/UX payload for API
│   ├── ux_scorer.py           # UX-oriented scoring
│   ├── screenshot_manager.py  # Per-run Playwright screenshots
│   ├── run_artifacts.py       # Traces, console logs, screenshot copies
│   ├── baseline_comparator.py # Compare runs
│   ├── page_quality.py        # Page-quality helpers
│   ├── ai_explainer.py        # Optional AI explanations
│   ├── deterministic_plan.py  # Deterministic smoke plan builder
│   ├── run_scan.py            # CLI / scan entry helpers
│   ├── run_system_diagnostic.py
│   ├── scheduler.py
│   ├── crawler/               # Site crawl, SPA, forms, elements
│   ├── core/                  # Browser, ecommerce_plan, micro_tasks, task_registry, login, etc.
│   ├── executor/              # Main executor, action_runner, task_executor, evidence, assertions
│   ├── executor/tools/        # navigation, form, browser, extraction, registry, runner
│   ├── planner/               # Planner, task_planner, schema_validator
│   ├── reporter/              # HTML/JSON reports, regression
│   ├── services/              # LLM client, defect intelligence, report_builder, insights
│   ├── agents/                # Evaluator agent
│   ├── db/                    # SQLAlchemy async PostgreSQL layer
│   └── models/                # action_log and related
├── frontend/
│   ├── package.json
│   ├── vite.config.js         # Dev server port 5173
│   └── src/
│       ├── App.jsx            # Routes
│       ├── main.jsx
│       ├── index.css
│       ├── config/api.js      # API base URL and paths
│       ├── pages/             # Dashboard, NewTest, LivePreview, Results, RunHistory, TestModules, etc.
│       ├── components/        # layout (Sidebar, Layout, TopBar), ui/*, charts, etc.
│       ├── hooks/             # useApi, useToast, useBackendHealth, …
│       └── data/              # mockData, backendAudit
├── shared/
│   ├── models/                # config, test_result, test_plan, site_model, run_record, …
│   ├── risk_scoring.py        # Severity weights (legacy helpers)
│   ├── pipeline_emit.py
│   └── utils/                 # auth, browser_stealth, url_utils, coverage, ai prompts
├── runs/                      # Per-run logs, result.json, screenshots (runtime)
├── qa-reports/                # Generated QA reports (when produced)
├── .qa-framework/             # Framework state (coverage, site model, plans; runtime)
├── pyproject.toml             # Python package metadata and dependencies
└── README.md                  # This file
```

### Tech Stack

**Backend:**

| Component | Technology |
|-----------|------------|
| API layer | FastAPI, Uvicorn |
| Browser automation | Playwright (Python) |
| Validation / models | Pydantic v2 |
| HTTP client | httpx (LLM APIs) |
| DB (optional) | SQLAlchemy 2 async + asyncpg |
| Env config | python-dotenv |
| CLI / logs | rich |
| Async IO | aiofiles |

**Frontend:**

| Component | Technology |
|-----------|------------|
| Framework | React 18 |
| Build | Vite 6 |
| Styling | Tailwind CSS 3 |
| Routing | react-router-dom 6 |
| Motion | framer-motion |
| Icons | lucide-react |
| Charts | recharts |

---

## Requirements

### System Requirements

- **Python** 3.11+ (per `pyproject.toml`: `requires-python = ">=3.11"`)
- **Node.js** 18+ recommended (for Vite 6 / local dev)
- **Playwright browsers** — install Chromium (and others if you extend browser types)

### Python Dependencies

Declared in `pyproject.toml` (install with `pip install .` or `pip install -e .` from the repo root):

- playwright, pydantic, faker, httpx, python-dotenv, fastapi, uvicorn[standard], aiofiles, rich, sqlalchemy[asyncio], asyncpg

Optional dev: ruff, pytest (`pip install -e ".[dev]"`).

### Node Dependencies

From `frontend/package.json`:

- react, react-dom, react-router-dom, framer-motion, lucide-react, recharts
- Dev: vite, @vitejs/plugin-react, tailwindcss, postcss, autoprefixer

---

## Installation & Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd Feuji
```

### 2. Backend Setup

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Unix/macOS:
# source venv/bin/activate

pip install .
# Optional dev tools:
# pip install -e ".[dev]"

playwright install chromium
```

There is no `requirements.txt` in this repo; dependencies are defined in `pyproject.toml`.

### 3. Frontend Setup

```bash
cd frontend
npm install
```

### 4. Environment Configuration

The API loads environment variables via `python-dotenv` (e.g. a `.env` file in the project root). Commonly referenced in code:

- **LLM (optional):** `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` — used when LLM features are enabled.
- **Database (optional):** `DATABASE_URL` for async PostgreSQL when DB-backed features are used.

The frontend can point at the API with:

- `VITE_API_URL` (defaults to `http://localhost:8000` in `frontend/src/config/api.js` if unset)

Example `frontend/.env.example` (if present) or create:

```env
VITE_API_URL=http://localhost:8000
```

---

## Running the Application

### Start Backend

```bash
uvicorn api.server:app --reload --port 8000
```

### Start Frontend

```bash
cd frontend
npm run dev
```

### Access the Application

- **Frontend UI:** http://localhost:5173 (configured in `frontend/vite.config.js`)
- **Backend API:** http://localhost:8000
- **OpenAPI docs:** http://localhost:8000/docs

---

## API Reference

Endpoints defined in `api/server.py`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/jobs/test.run` | Start a legacy job-style test run |
| GET | `/report/{report_id}` | Fetch shareable report payload |
| POST | `/synthetic/generate` | Generate synthetic data |
| GET | `/dashboard/summary` | Dashboard summary |
| GET | `/runs/history` | Run history listing |
| GET | `/results` | Aggregated results (legacy model) |
| GET | `/results/{job_id}` | Results for a job |
| GET | `/jobs/{job_id}/status` | Job status |
| GET | `/jobs/{job_id}/events` | Job events |
| GET | `/healthz` | Simple liveness |
| GET | `/health` | Health + API version (Nischay bridge) |
| POST | `/api/run` | Start QA run (Nischay body: url, depth, modules, tasks, device, auth) |
| GET | `/api/runs` | List runs |
| GET | `/api/runs/{run_key}` | Single run detail |
| GET | `/api/runs/{run_key}/status` | Run status for polling |
| GET | `/api/runs/{run_key}/logs` | Merged logs |
| GET | `/api/runs/{run_key}/stream` | SSE stream |
| GET | `/api/modules` | Module / flow metadata for UI |
| POST | `/api/runs/{run_key}/rerun` | Rerun from saved config |
| GET | `/api/runs/{run_key}/compare` | Baseline comparison vs previous run |
| GET | `/api/runs/{run_id}/screenshots` | Screenshot index JSON |
| GET | `/api/runs/{run_id}/screenshots/{filename}` | Serve PNG |

### Example: Start a Test

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-store.com",
    "depth": "standard",
    "modules": ["auth", "cart", "checkout"],
    "tasks": ["test login", "add item to cart"],
    "device": "desktop"
  }'
```

### Example Response

```json
{
  "run_id": "run_xxxxxxxxxx",
  "job_id": "run_xxxxxxxxxx",
  "status": "started",
  "url": "https://your-store.com"
}
```

(Exact fields match the handler return in `api/server.py` for `api_run`.)

---

## QA Modules

Micro-task IDs registered in `TASK_REGISTRY` (`backend/core/task_registry.py`):

| Module / task ID | Description |
|------------------|-------------|
| `login_user` | Login flow |
| `search_product` | Product search |
| `open_product_from_search` | Open PDP from search |
| `add_to_cart` | Add to cart |
| `apply_coupon` | Coupon application |
| `start_checkout` | Start checkout |
| `fill_address_form` | Address form |
| `place_order_attempt` | Place order (attempt) |
| `contact_support` | Support / contact |
| `check_page_load` | Page load check |
| `check_navigation_links` | Navigation links check |

Legacy flow IDs (mapped to tasks via `LEGACY_FLOW_TO_TASKS`): `auth`, `browse`, `cart`, `checkout`, `support`, `ui`, `product`, `navigation`, `search`, `coupon`.

---

## Task Presets

From `TASK_GROUPS` in `backend/core/task_registry.py`:

| Preset | Tasks (summary) | Use case |
|--------|-------------------|----------|
| `quick_scan` | search → open product → add to cart | Fast surface check |
| `conversion_scan` | cart → coupon → checkout → address | Conversion funnel |
| `auth_scan` | login | Auth-only run |
| `full_app_scan` | search, cart, coupon, checkout, order attempt, support | Broad sweep |

Aliases: `full_app`, `full`, `default` → `full_app_scan`.

---

## UX Scoring

Implemented in `backend/ux_scorer.py` and applied in `backend/structured_run_output.py`:

- **What it measures:** User experience impact of detected issues (e.g. conversion blockers, trust, navigation, performance feel), not a generic technical “genuinity” score.
- **Scores:** **UX score** 0–100 (100 = best experience). **Risk score** is defined as **100 − UX score** for legacy compatibility in summaries and gauges.
- **Labels:** Bands such as EXCELLENT UX, GOOD UX, NEEDS WORK, POOR UX, CRITICAL UX ISSUES (see `UX_SCORE_LABELS` in `ux_scorer.py`).
- **Categories:** Conversion Flow, Navigation & Findability, Page Clarity, Interaction Feedback, Error Recovery, Performance Feel, Mobile Usability, Accessibility, General — with configurable category weights.
- **Prioritization:** Issues receive penalties by type; `top_improvements` lists high-impact actions; `passed_checks` notes categories with no penalty in the run.

---

## Screenshots

_Add your own screenshots here._

Suggested captures:

- Dashboard
- New Test page
- Live Preview
- Results page (direct URL `/results` or `/results/:runId` still works; sidebar link removed by design)

---

## Roadmap

### Completed (MVP)

- FastAPI service with job and Nischay bridge endpoints
- Playwright-driven orchestrator pipeline and micro-tasks
- Structured issues, run registry, `runs/` artifacts
- UX scoring layer and screenshot APIs
- React SPA with core QA pages and API config

### In Progress / Partial

- AI-powered explanations when LLM env is configured (`ai_explainer`, `llm_client`)
- Visual/regression tooling via coverage and baseline utilities

### Planned (examples)

- SaaS-ready deployment and auth
- CI/CD integrations
- Team workflows
- Richer adaptive planning (planner hooks exist; depth varies)

---

## Contributing

1. Fork the repository  
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)  
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)  
4. Push to the branch (`git push origin feature/AmazingFeature`)  
5. Open a Pull Request  

---

## License

`pyproject.toml` currently lists **Proprietary** as the package license. If you intend open-source distribution, add a `LICENSE` file and align metadata. The template below is for projects that adopt MIT:

MIT License — see a `LICENSE` file in the repository when provided.

---

## Built With ❤️ by

Nischay AI — Making QA accessible to every e-commerce team.
