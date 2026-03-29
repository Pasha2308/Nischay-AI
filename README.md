<<<<<<< HEAD
Nischay AI

Autonomous QA Agent for Release Decisions

“Is this application safe to ship?”

Nischay AI is an AI-powered autonomous agent that navigates your application like a real user, executes actions, detects issues, and delivers a CTO-level decision report in seconds.

🚀 What Makes Nischay AI Different

❌ Not a test automation tool
❌ Not a crawler
❌ Not a script runner

✅ A decision engine for product release readiness

🔥 Core Capabilities
🧭 Real Browser Execution
Uses Playwright (headed mode)
Opens actual browser
Performs real user actions:
Click
Fill
Navigate
Submit
🤖 Autonomous Agent Behavior
Goal-driven execution (not random crawling)
Adapts based on task:
Auth
Checkout
Cart
Support
Thinks in user journeys
🔐 Smart Login Handling
Attempts programmatic login
Falls back to human-in-the-loop login
Detects login success automatically
Works on real-world SaaS + e-commerce apps
⚡ Micro-Task Execution (Fast Mode)

Run specific user actions in seconds:

Search product
Add to cart
Fill checkout
Contact support

👉 Each task runs in 10–20 seconds

🛍️ Full Journey Scans

Simulates full user journeys:

Browse → Product → Cart → Checkout
Auth flows
Support flows
UI integrity
🧠 Defect Detection Engine

Detects real issues:

Broken buttons / CTAs
Form failures
Navigation issues
Console errors
Missing validation
Performance issues
Broken images

Each issue includes:

Severity
Business impact (Revenue / Trust / UX / Data)
Fix suggestion
📊 Risk Scoring System

Outputs:

Score: 0–100
Level: CRITICAL / HIGH / MEDIUM / LOW

👉 Helps answer:

“Should we ship this?”

📜 Action Trail (Proof Layer)

Every action is recorded:

What happened
Where
Result
Duration

👉 “You can see what the AI did”

🧾 Executive Report
3-line CTO summary
Defect list
Recommendations
Scorecards

👉 Boardroom-ready output

🏗️ Architecture
User Input
   ↓
Task Engine (Agent Brain)
   ↓
Execution Layer (Playwright)
   ↓
Flow System (Auth / Cart / Checkout / etc.)
   ↓
Detection Engine
   ↓
Risk Engine
   ↓
Report Builder
   ↓
Frontend (Live Logs + Results)
⚙️ Installation
1. Clone Repo
git clone https://github.com/Pasha2308/Nischay-AI.git
cd Nischay-AI
2. Backend Setup
pip install -r requirements.txt
playwright install
3. Run Backend
uvicorn api.server:app --reload
4. Frontend Setup
cd frontend
npm install
npm run dev

Open:

http://localhost:5173
🧪 Usage
🔹 Full Scan Mode
Enter URL
Select scan type:
Quick Scan
Conversion Flow
Authentication Flow
Full App Scan
Click Launch Scan
⚡ Micro Task Mode (Recommended)

Run focused actions:

Search Product
Add to Cart
Checkout Form
Contact Support

👉 Faster, reliable, demo-friendly

🎯 Example
{
  "url": "https://automationexercise.com",
  "task_type": "micro",
  "micro_task": "add_to_cart"
}
📊 Output Example
Scan covered 6 pages and found 12 issues.
Critical checkout failure blocks purchases.
Fix checkout button logic immediately.
🧠 Tech Stack
Backend: Python, FastAPI
Browser: Playwright
Frontend: React + Vite
AI: LLM-based analysis
Architecture: Agent-driven system
⚡ Performance
Mode	Time
Micro Task	10–20 sec
Full Scan	60–90 sec
🚨 Limitations
Complex login flows may require manual login
Highly dynamic apps may need tuning
Checkout flows vary across sites
🛣️ Roadmap
Smarter agent reasoning logs
Session-aware flows
Multi-session testing
AI decision explanation layer
SaaS dashboard
👨‍💻 Author

Mohammed Pasha
Founder & Builder

GitHub: https://github.com/Pasha2308
LinkedIn: Pasha23
⭐ Final Note

Nischay AI is not about testing.

It’s about making release decisions with confidence.
=======
# Nischay AI — Autonomous QA Decision Engine

**Nischay AI** is an autonomous quality-assurance system that drives a **real browser** like a user, observes what happens, and returns a **shipping decision**—not a pass/fail test matrix. It is built for teams that need actionable risk signals fast, especially on **e-commerce** flows.

---

## What it does

- An **agent-style pipeline** simulates real user behavior in the browser (navigation, forms, cart/checkout paths, and more via **micro-tasks**).
- The system aggregates observations and applies a **decision engine** to output a clear verdict: **SAFE**, **CAUTION**, or **DO NOT SHIP**, with risk context and evidence—not “42 tests passed.”
- It is **not** a generic unit-test runner: it is a **browser-grounded QA decision** product.

---

## Core concept

```
User → Intent (URL + task bundle) → Agent pipeline → Browser (Playwright)
     → Actions → Observations → Decision + logs
```

The frontend collects intent; the backend orchestrates crawl/plan/execute; **Playwright** runs against the live site; structured results feed the **decision** layer and the UI.

---

## Features

| Area | Description |
|------|-------------|
| **Micro Task Engine** | Composable tasks (search, cart, checkout, support, etc.) grouped into scan presets (`quick_scan`, `conversion_scan`, `full_app_scan`). |
| **Real browser execution** | **Playwright** with optional **Chromium** (default), **Firefox**, or **WebKit**—same tasks, selected engine. |
| **Decision engine** | Risk-based **SAFE / CAUTION / DO NOT SHIP** style output from execution snapshots. |
| **Live logs** | Streaming-style job events for transparency during runs. |
| **E-commerce focus** | Task registry and flows tuned for typical storefront journeys. |

---

## Architecture

| Layer | Stack |
|-------|--------|
| **Frontend** | React (Vite), dashboard, test launcher, results |
| **Backend API** | FastAPI (`api/server.py`) |
| **Agent engine** | Orchestrator, micro-task runner, crawl/plan/execute pipeline (`backend/`) |
| **Browser** | Playwright (`backend/core/browser.py` centralizes launch) |
| **Decision engine** | Rules/snapshot assembly (`backend/core/`, services) |
| **Shared models** | Pydantic config and DTOs (`shared/`) |

---

## Project structure

```
.
├── api/              # FastAPI app (HTTP API, job orchestration)
├── backend/          # Crawler, executor, orchestrator, micro-tasks, services
│   └── core/         # Browser launch, ecommerce plans, task registry, etc.
├── frontend/         # React SPA
├── shared/           # Cross-cutting models and utilities
└── pyproject.toml    # Python package and dependencies
```

---

## How to run

### Prerequisites

- **Python 3.11+**
- **Node.js** (LTS recommended) for the frontend
- **Playwright browsers** (install after Python deps)

### Backend

From the repository root:

```bash
pip install -e .
playwright install chromium firefox webkit
```

Start the API (reload for development):

```bash
uvicorn api.server:app --reload
```

Default API base: `http://localhost:8000` (see `frontend` service `API_BASE` if you change the port).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the printed local URL (typically `http://localhost:5173`).

---

## How to use

1. Open **`/test`** in the app (or use the **New test** nav entry).
2. Enter a **URL** (`http://` or `https://`).
3. Choose a **task group** (e.g. full app scan) or **Advanced** micro-tasks.
4. Optionally pick **Browser** (Chromium default, or Firefox / WebKit).
5. **Start test** — you are redirected to **results** for the job id when the run is queued.

The **Dashboard** (`/`) shows session stats; **Run history** lists recent completed runs (in-memory for the current API process).

---

## Example output

Execution payloads include a structured snapshot; conceptually:

```json
{
  "decision": "DO NOT SHIP",
  "risk": "HIGH",
  "summary": "Checkout blocked payment step; cart actions succeeded but fulfillment path is unsafe to release."
}
```

Exact field names match `execution_snapshot` in API responses and the React types in `frontend/src/services/backend-service.ts`.

---

## API: optional `browser_type`

`POST /jobs/test.run` accepts an optional JSON field:

```json
{
  "url": "https://example.com",
  "scan_task": "full_app_scan",
  "browser_type": "chromium"
}
```

Allowed values: `"chromium"` (default), `"firefox"`, `"webkit"`. Omitted means **Chromium**.

---

## Development rules (team norms)

- Prefer **small, reviewable changes**; avoid drive-by refactors.
- **Cursor / AI-assisted coding** is fine; keep prompts and reviews disciplined.
- Prefer **real target URLs** for integration checks; avoid relying on fabricated payloads for “does the pipeline run?”
- **Browser selection** must not fork task logic—only the Playwright launch target changes.

---

## Roadmap

- Expand **micro-task** coverage and presets
- More **adaptive** flows (guided by LLM where configured)
- **CI/CD** hooks (API-first) for gates on merge/release

---

## Contributing

1. Fork / branch from `main`.
2. Install backend with `pip install -e ".[dev]"` if you use optional dev tools.
3. Run the frontend build: `cd frontend && npm run build`.
4. Open a PR with a clear description of behavior and risk.

---

## License

MIT
>>>>>>> b51165b (feat: synthetic data + risk score + UI improvements)
