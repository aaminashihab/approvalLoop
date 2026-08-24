# ApprovalLoop — Fortified Enterprise Fleet (Devpost Submission)

## 🏷️ Basic Project Information

- **Project Title:** ApprovalLoop — Fortified Enterprise Fleet Upgrade
- **Tagline / Elevator Pitch:** Deterministic execution governance gateway for autonomous AI agent fleets: AI proposes, deterministic policy decides, infrastructure executes.
- **Track:** Taskmaster & Institutional Agents

---

## 💡 Inspiration & Problem

Modern enterprises are actively deploying fleets of autonomous AI agents across finance, customer support, and sales. However, granting LLMs direct tool-execution privileges exposes critical vulnerabilities:
1. **Unauthorized Financial Action:** A single hallucination or prompt injection can authorize an unauthorized refund, wire transfer, or discount.
2. **Silent Operational Drag:** Stalled approval requests in human inboxes silently halt operations.
3. **Session Amnesia:** Multi-step asynchronous workflows that require human sign-off lose context across container restarts.
4. **Duplicate Execution:** Distributed systems experience worker crashes, timeouts, and duplicate queue deliveries.

ApprovalLoop was built on a fortified foundational principle:
> **“AI proposes. Deterministic policy decides. Infrastructure executes.”**

---

## ⚙️ What ApprovalLoop Does

ApprovalLoop acts as the **Fortified Execution Governance Gateway** for enterprise AI agent fleets:

1. **Gemini Agent Fleet:** Orchestrates specialized institutional agents (**Finance Agent**, **Support Agent**, **Sales Agent**) built with **Google Gemini 3.5** and the **Google GenAI SDK** (`google-genai`).
2. **Zero-Trust Agent Identity:** Authenticates agent requests using **HMAC-SHA256** cryptographic signatures and **Google Cloud IAM OIDC** tokens, checking against a Firestore-backed **Agent Registry** capability whitelist.
3. **Model Safety Guardrails (Model Armor):** Intercepts prompt injections, adversarial overrides, and secret leakage before and after LLM inference.
4. **Deterministic Policy Engine:** Enforces immutable, reproducible, versioned policy profiles (`finance-v3`, `support-v1`, `sales-v1`) with mathematical `Decimal` precision:
   - **Case A (< ₹5,000 / $50):** `ALLOW` $\rightarrow$ Automatic execution.
   - **Case B (₹5,000–₹25,000 / $50–$250):** `REQUIRE_HUMAN_APPROVAL` $\rightarrow$ Workflow pauses in Memory Bank, queued for human operator sign-off.
   - **Case C (> ₹25,000 / $250):** `DENY` $\rightarrow$ Blocked deterministically, even if Gemini recommends it.
5. **Persistent Memory Bank:** Preserves cross-session workflow state, action history, previous decisions, and tool results in **Google Cloud Firestore**, enabling paused workflows to resume seamlessly after human sign-off.
6. **Leased Async Runtime & Crash Recovery:** Uses processing leases, idempotency keys, and expired-lease recovery routines to guarantee resilience against worker crashes and duplicate deliveries.
7. **Autonomous Background Chasing:** Cloud Scheduler wakes the autonomous engine to monitor stalled approvals and escalate unprompted (**0 human prompts required**).
8. **OpenTelemetry Observability:** Distributed spans and runtime AgBOM inventory reconstructing full execution causality.

---

## 🏛️ Architecture & Tech Stack

- **Model:** Google Gemini 3.5 Flash (`gemini-3.5-flash`)
- **Agent Framework:** Google GenAI SDK (`google-genai` Python library)
- **Backend Service:** FastAPI + Python 3.10 with strict Pydantic v2, `Decimal` monetary precision, OpenTelemetry tracer
- **Frontend Dashboard:** React 18 + TypeScript + Vite + Tailwind CSS + Lucide Icons
- **Google Cloud Platform:**
  - **Google Cloud Run:** Serverless container host
  - **Google Cloud Firestore:** Scalable NoSQL store for Agent Registry, Memory Bank, and Outbox
  - **Google Cloud Scheduler:** Managed serverless cron trigger
  - **Google Secret Manager:** Secure secret injection

---

## 🧪 Verification & Scale Benchmark

- **103 Automated Pytest Tests Passing (100% Pass Rate)**
- **1,000-Report Scale Benchmark:** 1,000 concurrent synthetic approval lifecycles evaluated in 0.25s (local test environment) with 0 duplicate sends and 0 state corruptions.
- **Critical Demo Scenarios:** Automated tests and interactive UI verifying Case A (Auto-ALLOW), Case B (Human Sign-Off), and Case C (Deterministic DENY).

---

## 🎬 4-Minute Demo Highlights

1. **Agent Fleet Overview:** Inspect live status, risk tiers, and whitelisted capabilities for Finance, Support, and Sales agents.
2. **Case A (Refund ₹2,000):** Agent proposes $\rightarrow$ Identity Verified $\rightarrow$ Policy allows $\rightarrow$ Instant execution.
3. **Case B (Refund ₹20,000):** Agent proposes $\rightarrow$ Policy halts for sign-off $\rightarrow$ Workflow pauses in Memory Bank $\rightarrow$ Operator approves in UI $\rightarrow$ Execution resumes.
4. **Case C (Refund ₹100,000):** Agent proposes $\rightarrow$ Deterministic policy rejects $\rightarrow$ Model cannot bypass governance.
5. **Memory Bank & Traces:** Inspect persistent cross-session history and OpenTelemetry spans.
