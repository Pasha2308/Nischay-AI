# 🚀 Nischay AI — Autonomous QA Decision Engine

## 📌 Overview
Nischay AI is an autonomous QA agent that simulates real user behavior on web applications and answers one critical question:

👉 **“Is this application safe to ship?”**

Instead of logs or test cases, Nischay AI outputs:
- **Decision** (SAFE / CAUTION / DO NOT SHIP)
- **Risk Score** (0–100)
- **Business Impact**
- **Actionable Fix Suggestions**

---

## 🎯 Core Idea
Traditional QA tools detect issues.

Nischay AI:
👉 Acts like a real user  
👉 Executes real flows  
👉 Makes a product-level decision  

Flow:
**User → Intent → AI Agent → Browser → Actions → Observations → Decision**

---

## 🧠 Core Features

### ✅ Autonomous Discovery
- Simulates real user journeys using a real browser (Playwright)
- Executes micro tasks (search, product, cart, checkout, support, UI)
- Goal-based fallback logic for resilient interaction (behaves like a user, not a brittle script)

### ⚡ Defect Scoring
- Risk scoring system (0–100)
- Severity: critical / high / medium / low
- Business impact classification: revenue / trust / ux / compliance / performance
- Canonical defect schema with actionable descriptions and fixes

### 📊 Visualization
- Decision-focused dashboard
- Execution timeline + live log streaming
- Defects + fix suggestions in a clean UI
- Issues Tracker (DB-backed) with status: open / resolved / ignored

### 🧪 Synthetic Data Generation
- Dynamic user profiles
- Search queries
- Form inputs for realistic flows

---

## 🏗️ Architecture

Frontend (React)  
↓  
Backend (FastAPI)  
↓  
Orchestrator  
↓  
Micro Task Engine  
↓  
Playwright Browser  
↓  
Decision Engine  

---

## 📁 Project Structure

- `backend/` → Orchestrator, crawler, micro tasks, scoring, services
- `api/` → FastAPI server + endpoints
- `frontend/` → React UI (Vite)
- `shared/` → Shared models + utilities

---

## ⚙️ Prerequisites

- **Python** 3.10+ (recommended 3.11+)
- **Node.js** 18+
- **npm**
- **Playwright** (Chromium browser installed)

---

## 🛠️ Setup Instructions

### 1. Clone repository

```bash
git clone https://github.com/Pasha2308/Nischay-AI
cd Nischay-AI
```

### 2. Backend (FastAPI)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -e .
python -m playwright install chromium
```

### 3. Frontend (React)

```bash
cd frontend
npm install
```

---

## ▶️ Running Nischay AI (Local)

### Start backend (recommended on Windows)

`run_backend.py` cleans up port 8000 and starts the API.

```bash
python run_backend.py
```

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`

### Start frontend

```bash
cd frontend
npm run dev
```

- UI: `http://localhost:5173` (preferred; falls back if taken)

---

## ✅ Demo Flow (What judges should try)

1. Open the UI: `http://localhost:5173`
2. Go to **New Test**
3. Enter: `https://automationexercise.com`
4. Select flows (Auth/Browse/Cart/Checkout/Support/UI)
5. Click **Launch**
6. Verify:
   - Live logs stream during execution
   - Results page shows **Decision + Risk Score**
   - Defects include **specific titles + page URLs + fix suggestions**
7. Explore:
   - **Issues Tracker** → deduped defects (open/resolved/ignored)
   - **Analytics** → charts stay populated (DB or demo fallback)
   - **Integrations** → API key generation + GitHub Actions YAML
   - **Settings** → BYO LLM configuration (optional)

---

## 🔌 API (Quick Reference)

Use `http://localhost:8000/docs` for full schemas.

- **Run a scan (UI jobs)**
  - `POST /jobs/test.run`
  - `GET /results/{job_id}`
  - `GET /jobs/{job_id}/events`

- **Issues Tracker**
  - `GET /issues`
  - `GET /issues/stats`
  - `GET /issues/{id}`
  - `PATCH /issues/{id}`

- **Integrations (API keys + /v1 scans)**
  - `POST /api-keys`
  - `GET /api-keys`
  - `DELETE /api-keys/{id}`
  - `POST /v1/scan` (API key protected)

---

## 🔒 Security & Data Handling (Hackathon-ready notes)

- API keys are **generated once** and stored **hashed** (bcrypt).
- LLM API keys (if configured) are stored **encrypted** (Fernet).
- Defects are stored in a DB-friendly schema and deduped by `(page_url, title)`.

---

## 🧩 Tech Stack

- **Backend**: FastAPI, Uvicorn, Playwright, Pydantic, SQLAlchemy (optional), APScheduler (optional)
- **Frontend**: React, Vite, Tailwind, Recharts

---

## 📄 License

Hackathon project — add a license if you plan to open-source publicly.
