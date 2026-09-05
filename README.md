# RecoverOS

**Autonomous Revenue Recovery Decision & Experimentation Engine**

RecoverOS is an intelligent, agentic AI layer designed to sit between a merchant's payment gateway (Razorpay) and their customer communication channels. It replaces blind, fixed-interval payment retries with contextual, safety-first autonomous recovery decisions.

Built for the **Razorpay AI Buildathon — Track 3: AI Revenue Recovery**.

---

## 🎯 The Problem

When a payment fails (e.g., due to insufficient funds, bank downtime, expired cards), most businesses either:
1. Blindly retry the payment using fixed rules (e.g., "retry every 24 hours").
2. Spam the customer with generic "Your payment failed" emails.

This brute-force approach leads to:
- High customer friction and fatigue.
- Wasted communication costs.
- Increased risk of duplicate charges or bank penalizations.
- Missed revenue because the recovery strategy didn't match the root cause of the failure.

## 🚀 The Solution

RecoverOS solves this by treating every failed payment as an **economic optimization problem** bound by **safety guardrails**.

When a payment fails, RecoverOS:
1. **Diagnoses** the true root cause (e.g., was it a hard decline like an expired card, or a soft decline like bank downtime?).
2. **Analyzes** the customer's payment history and lifetime value.
3. **Predicts** the probability of recovery for every possible action (retry now, send WhatsApp link, offer discount, etc.).
4. **Calculates** the Expected Net Revenue: `(Probability × Amount) - (Communication Cost + Discount + Fatigue Penalty)`.
5. **Checks** merchant safety policies (e.g., quiet hours, max touchpoints, high-value approval thresholds).
6. **Executes** the highest-value action autonomously, or routes it to a human for approval.
7. **Learns** from the outcome using a Contextual Bandit algorithm to improve future decisions.

---

## 🧠 Key Differentiators (Why it's not just a "retry bot")

1. **Root-Cause Intelligence**: Doesn't just retry. It knows an *Expired Card* needs a payment link, while *Bank Downtime* needs a delayed silent retry.
2. **Recovery Economics Engine**: Every action is priced. Sending an SMS costs money. Bothering a VIP customer costs goodwill. RecoverOS calculates the true *Net* Expected Value of an action.
3. **Merchant Policy Center (Circuit Breakers)**: Strict, deterministic guardrails. If it's 11 PM (Quiet Hours) or the transaction is marked as `SUSPECTED_FRAUD`, the AI is physically blocked from executing.
4. **Contextual Bandit Learning**: The system isn't static. It learns which channels and strategies work best for specific customer segments over time.
5. **Human-in-the-Loop**: High-value transactions (e.g., B2B invoices > ₹50,000) are automatically routed to the **Approvals Queue** for human review, preventing the AI from making high-risk autonomous decisions.

---

## 🏗 Architecture

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for a deep dive into the 4-Agent pipeline, ML models, and safety gates.

### Tech Stack
- **Backend**: Python, FastAPI, SQLAlchemy (Async), SQLite
- **Machine Learning**: Scikit-Learn (GradientBoostingClassifier, LogisticRegression)
- **Frontend**: React 19, Vite, Recharts, Vanilla CSS (Glassmorphism design)
- **Integrations**: Mock Razorpay Client (ready for real Webhook ingestion)

---

## 🏎 Quick Start

### 1. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Start the API server
# Note: On first startup, it will automatically train the ML model from synthetic data.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### 3. Usage
Navigate to `http://localhost:5173/` in your browser.

---

## 📊 Evaluation & Benchmarking

RecoverOS includes a built-in **Evaluation Lab** that runs a synthetic benchmark of 2,000 transactions comparing the RecoverOS AI pipeline against a standard "Fixed 24h Retry" baseline.

Typical benchmark results show:
- **+15-20%** Recovery Rate Lift
- **-30%** Reduction in customer messages (less spam)
- **Zero** duplicate charges (due to strict Idempotency guards)

---

## 🎬 5-Minute Demo Guide

See [DEMO.md](docs/DEMO.md) for the exact script and flow to demonstrate the platform.

---

## 🔒 Security & Safety

- **Idempotency**: All execution requests require a unique SHA-256 hash `(transaction_id + action_type + time_window)` to prevent duplicate charges.
- **Fraud Protection**: The `failure_classifier` maps risk codes to `SUSPECTED_FRAUD`. The Executor Agent has a hard-coded block against running recovery on fraud.
- **LLM Safety**: The AI does *not* have direct access to charge credit cards. It outputs a proposed action enum, which is then routed through deterministic, auditable Python policy checks before execution.
