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
