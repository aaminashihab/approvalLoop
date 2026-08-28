# ApprovalLoop — Governance for Autonomous Enterprise Agent Fleets

> **AI proposes. Deterministic policy decides. Infrastructure executes.**

**ApprovalLoop is a governed control plane for autonomous enterprise agents that enforces deterministic policy, human approval, persistent state, and auditable execution before agents can trigger real-world side effects.**

---

## 🏷️ Basic Project Information

- **Project Title:** ApprovalLoop — Governance for Autonomous Enterprise Agent Fleets
- **Tagline / Elevator Pitch:** Control plane for autonomous AI agent fleets: AI proposes, deterministic policy decides, infrastructure executes.
- **Track:** Fortified Enterprise Fleet

---

## 💡 Inspiration & Problem

Modern enterprises are actively deploying fleets of autonomous AI agents across finance, customer support, and sales. However, granting LLMs direct tool-execution privileges exposes critical vulnerabilities:
1. **Unauthorized Financial Action:** A single hallucination or prompt injection can authorize an unauthorized refund, wire transfer, or discount.
2. **Silent Operational Drag:** Stalled approval requests in human inboxes silently halt operations because nobody prompts a conversational assistant when an approver is out of office.
3. **Session Amnesia:** Multi-step asynchronous workflows that require human sign-off lose context across container restarts.
4. **Duplicate Execution:** Distributed systems experience worker crashes, timeouts, and duplicate queue deliveries.

ApprovalLoop was built on a fortified foundational principle:
> **“AI proposes. Deterministic policy decides. Infrastructure executes.”**

---

## ⚙️ What ApprovalLoop Does

ApprovalLoop acts as the **Fortified Execution Governance Gateway** for enterprise AI agent fleets:

1. **Gemini Agent Fleet:** Orchestrates specialized institutional agents (**Finance Agent**, **Support Agent**, **Sales Agent**) built with **Google Gemini 3.5 Flash** (`gemini-3.5-flash`) and the **Google GenAI SDK** (`google-genai`).
2. **Zero-Trust Agent Identity:** Authenticates agent requests using **HMAC-SHA256** cryptographic signatures and **Google Cloud IAM OIDC** tokens, checking against a Firestore-backed **Agent Registry** capability whitelist.
3. **Google Cloud Model Armor Integration:** Intercepts prompt injections, adversarial overrides, and secret leakage before and after LLM inference via official `google-cloud-modelarmor` APIs.
4. **Deterministic Policy Engine:** Enforces immutable, reproducible, versioned policy profiles (`finance-v3`, `support-v1`, `sales-v1`) with mathematical `Decimal` precision:
   - **Case A (< ₹5,000):** `ALLOW` $\rightarrow$ Automatic execution permitted.
   - **Case B (₹5,000–₹25,000):** `REQUIRE_HUMAN_APPROVAL` $\rightarrow$ Workflow pauses in Memory Bank, queued for human sign-off.
   - **Case C (> ₹25,000):** `DENY` $\rightarrow$ Blocked deterministically, even if Gemini recommends it.
   *(Note: Configurable policy engine also supports USD and multi-currency normalization profiles).*
5. **Persistent Memory Bank:** Preserves cross-session workflow state, action history, previous decisions, and tool results in **Google Cloud Firestore**, enabling paused workflows to resume seamlessly after human sign-off.
6. **Leased Async Runtime & Crash Recovery:** Uses processing leases, idempotency keys, and expired-lease recovery routines to guarantee resilience against worker crashes and duplicate deliveries.
7. **Autonomous Background Chasing:** Cloud Scheduler wakes the autonomous engine to monitor stalled approvals and escalate unprompted (**0 human prompts required**).
8. **OpenTelemetry Observability:** Distributed spans and runtime AgBOM inventory reconstructing full execution causality.

---

## 🏛️ Architecture & Tech Stack

- **Model:** Google Gemini 3.5 Flash (`gemini-3.5-flash`)
- **Agent Framework:** Google GenAI SDK (`google-genai` Python library)
- **Safety Guardrail:** Google Cloud Model Armor API (`google-cloud-modelarmor`)
- **Backend Service:** FastAPI + Python 3.10 with strict Pydantic v2, `Decimal` monetary precision, OpenTelemetry tracer
- **Frontend Dashboard:** React 18 + TypeScript + Vite + Tailwind CSS + Lucide Icons
- **Google Cloud Platform:**
  - **Google Cloud Run:** Serverless container host
  - **Google Cloud Firestore:** Scalable NoSQL store for Agent Registry, Memory Bank, and Outbox
  - **Google Cloud Scheduler:** Managed serverless cron trigger (`*/1 * * * *`)
  - **Google Secret Manager:** Secure secret injection

### 🤖 Google Agent Framework Compliance

| Requirement | Implementation | Repository Path | Purpose |
| :--- | :--- | :--- | :--- |
| **At least one Google Agent Framework** | **Google GenAI SDK (`google-genai`)** | `backend/approval_loop/agent/fleet.py`<br>`backend/approval_loop/agent/drafter.py` | Context analysis, structured action proposal formulation, risk assessment, multi-agent delegation, and notification wording generation |

---

## 🧪 Verification & Scale Benchmark

- **128 Automated Backend Unit, Integration, and Framework Tests Passing Clean (100% Pass Rate)**
- **Verification Evidence:** The repository provides verified implementation evidence for all three mandatory technology requirements, with 128 backend tests passing.
- **Synthetic Scale Benchmark:** Processed 1,000 approval reports through the workflow simulation in 0.22s (`test_large_scale_simulation.py`), with 0 duplicate actions, 0 invalid state transitions, 0 unauthorized sends, and 0 state corruptions.
- **Critical Demo Scenarios:** Automated tests (`test_agent_framework.py`, `test_enterprise_demo_scenarios.py`) and interactive UI verifying Case A (Auto-ALLOW), Case B (Human Sign-Off), and Case C (Deterministic DENY).

---

## 🎬 4-Minute Demo Highlights

1. **Agent Fleet Overview:** Inspect live status, risk tiers, and whitelisted capabilities for Finance, Support, and Sales agents.
2. **Case A (Refund ₹2,000):** Agent proposes $\rightarrow$ Identity Verified $\rightarrow$ Model Armor inspects $\rightarrow$ Policy allows $\rightarrow$ Instant execution.
3. **Case B (Refund ₹20,000):** Agent proposes $\rightarrow$ Policy halts for sign-off $\rightarrow$ Workflow pauses in Memory Bank $\rightarrow$ Operator approves in UI $\rightarrow$ Execution resumes.
4. **Case C (Refund ₹100,000):** Agent proposes $\rightarrow$ Deterministic policy rejects $\rightarrow$ Model cannot bypass governance.
5. **Memory Bank & Traces:** Inspect persistent cross-session history in Firestore and OpenTelemetry spans.
