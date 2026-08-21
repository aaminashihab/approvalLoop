# 🚀 ApprovalLoop — Fortified Enterprise Fleet Upgrade

**ApprovalLoop is a deterministic execution governance gateway for autonomous AI agent fleets.**

> **Core Architectural Invariant:**
> **AI proposes. Deterministic policy decides. Infrastructure executes.**

ApprovalLoop bridges autonomous intelligence (**Google Gemini 3.5**, **Google Agent Framework**) with deterministic corporate governance, zero-trust cryptographic identity, persistent memory banks, leased async execution, and mathematical safety gates.

---

## 📌 1. The Problem

Autonomous AI agents are transitioning from conversational chatbots into institutional operators capable of taking real-world actions: issuing financial refunds, approving expenses, granting sales discounts, and updating ERP ledgers.

However, deploying autonomous agents directly to production tools creates existential enterprise risks:
1. **Direct Tool Authority:** When LLMs are equipped with direct tool-calling privileges, a single prompt injection, model hallucination, or ambiguous context can execute irreversible, unauthorized financial or state changes.
2. **Silent Workflow Stalls:** Stalled human approvals in enterprise systems silently halt operations because nobody prompts a conversational assistant when an approver is out of office.
3. **Session Amnesia:** Multi-step asynchronous workflows that require human sign-off lose context across disconnections or container restarts.
4. **Duplicate Execution:** Network timeouts and overlapping scheduler invocations cause duplicate side-effect execution.

---

## 💡 2. Why Autonomous Agents Need Execution Governance

Non-deterministic models are brilliant at reasoning, context comprehension, and proposal formulation. They must **never** hold authoritative authorization over money, database state, or external side effects.

ApprovalLoop enforces an absolute separation of concerns:

| Responsibility | Component | Implementation |
| :--- | :--- | :--- |
| **Reasoning & Proposals** | **Gemini Agent Fleet** | Gemini 3.5 via Google GenAI SDK emits structured `AgentActionProposal` |
| **Identity & Authentication** | **Agent Identity Layer** | HMAC-SHA256 & Google Cloud IAM OIDC zero-trust token verification |
| **Prompt & Payload Defense** | **Model Safety Guardrail** | Model Armor / Safety filters intercept prompt injections & secret leaks |
| **Parameter Integrity** | **4-Point Safety Validator** | Deterministic mathematical checks (exact Decimal precision, ID matching) |
| **Authorization Policy** | **Policy Engine** | Versioned deterministic profiles (`finance-v3`, `support-v1`, `sales-v1`) |
| **Execution Governance** | **ApprovalLoop Gateway** | Emits `ALLOW`, `REQUIRE_HUMAN_APPROVAL`, or `DENY` decisions |
| **Persistent Context** | **Memory Bank** | Firestore-backed cross-session state, action history, and pause/resume |
| **Asynchronous Execution** | **Async Runtime & Workers** | Leased task execution with crash recovery and idempotency keys |
| **Audit & Observability** | **OpenTelemetry** | Distributed traces and audit ledger reconstructing full causality |

---

## 🏗️ 3. Target Architecture Diagram

```text
                       GEMINI AGENT FLEET
         ┌─────────────────────┼─────────────────────┐
   Finance Agent         Support Agent         Sales Agent
 (Refunds/Expenses)    (Credits/Escalations)  (Discounts/Terms)
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │ Structured Proposal
                               ▼
                      ┌─────────────────┐
                      │ AGENT REGISTRY  │
                      │ & IDENTITY AUTH │
                      └────────┬────────┘
                               │ Verified Identity (HMAC / OIDC)
                               ▼
                      ┌─────────────────┐
                      │  AGENT GATEWAY  │
                      │  (ApprovalLoop) │
                      └────────┬────────┘
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
          Model Safety      Policy        Deterministic
           Guardrail        Engine          Validator
         (Model Armor)  (Domain/Limits)  (Facts/Types)
               │               │               │
               └───────────────┼───────────────┘
                               │
                               ▼
                      Gateway Authorization
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
               ALLOW               REQUIRE_HUMAN_APPROVAL
                 │                           │
                 │                     Workflow Pauses
                 │                           │
                 │                     Human Decision
                 │                     (Approve/Reject)
                 │                           │
                 └─────────────┬─────────────┘
                               │ Resumed
                               ▼
                      ASYNC RUNTIME / WORKER
                    (Idempotent, Leased Claims)
                               │
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
            External APIs  Notifications  Firestore State
                 │
                 ▼
          MEMORY BANK (Persistent Cross-Session Context)
                 │
                 ▼
       AUDIT LEDGER & OPENTELEMETRY TRACES
```

---

## 🤖 4. Gemini Agent Fleet

ApprovalLoop orchestrates a scalable network of specialized institutional agents built on the **Google Agent Framework (Google GenAI SDK `google-genai`)** with **Gemini 3.5 Flash**:

1. **Finance Agent (`finance-agent` v1.2.0):** Evaluates corporate refund claims, invoice anomalies, and stalled expense approvals. Formulates structured proposals (`issue_refund`, `approve_expense`, `escalate_stalled_approval`).
2. **Support Agent (`support-agent` v1.1.0):** Evaluates customer SLA disputes and service outages. Formulates structured compensation proposals (`credit_account`, `escalate_ticket`, `sla_override`).
3. **Sales Agent (`sales-agent` v1.0.0):** Evaluates enterprise contract terms and ARR margins. Formulates structured commercial discount proposals (`grant_discount`, `waive_fee`, `custom_contract_terms`).

**Zero Direct Tool Access:** Fleet agents have **zero** direct network access to databases or payment APIs. Every proposed action is emitted as a strictly typed Pydantic `AgentActionProposal` and submitted to the Gateway.

---

## 🗄️ 5. Real Agent Registry

Persistent in **Google Cloud Firestore**, the Agent Registry defines the identity, capabilities, and boundaries of every fleet member:

```json
{
  "agent_id": "finance-agent",
  "name": "Institutional Finance Agent",
  "description": "Autonomous financial operations agent proposing refunds and expense adjustments.",
  "owner": "finance-ops@company.internal",
  "version": "1.2.0",
  "status": "active",
  "capabilities": ["financial_reasoning", "expense_analysis", "refund_assessment"],
  "allowed_tools": ["payment_gateway", "erp_ledger", "notification_worker"],
  "allowed_actions": ["issue_refund", "approve_expense", "escalate_stalled_approval"],
  "policy_profile": "finance-v3",
  "risk_level": "high"
}
```

The Registry exposes secure administrative endpoints at `/api/registry/agents` to register, inspect, update, and enable/disable institutional agents.

---

## 🔐 6. Agent Identity & Zero-Trust Access Control

Requests to the Gateway require authenticated cryptographic identity rather than trusting arbitrary headers:
- **HMAC-SHA256 Token Provider:** Cryptographically signs and verifies agent requests with timestamp-based replay attack mitigation.
- **Google Cloud IAM OIDC Verification:** Verifies Google Cloud Service Account identity tokens in production.
- **Verification Invariants:**
  1. Cryptographic token signature is valid and unexpired.
  2. Agent exists in Registry and status is `ACTIVE`.
  3. Running agent version matches registered specification.
  4. Requested action is explicitly in the agent's `allowed_actions` whitelist.

---

## ⛩️ 7. ApprovalLoop Agent Gateway

The Gateway is the unified execution gatekeeper:
```python
decision = gateway.authorize_action(proposal, auth_context)
```

The Gateway returns structured decisions:
- **`ALLOW`**: Low-risk action within autonomous policy limits $\rightarrow$ automatically queued and executed.
- **`REQUIRE_HUMAN_APPROVAL`**: Consequential action exceeding autonomous threshold $\rightarrow$ workflow paused in Memory Bank, queued for human sign-off in Dashboard.
- **`DENY`**: Violation of financial ceilings, domain whitelists, or security boundaries $\rightarrow$ deterministically blocked, audited, and terminated.

---

## 📜 8. Deterministic Policy Engine with Versioned Profiles

Policy decisions are 100% deterministic, immutable, and reproducible from structured input:

### Profile: `finance-v3`
- **$<\text{INR } 5,000$ ($<\$50$):** `ALLOW` (Automatic execution)
- **$\text{INR } 5,000–\text{INR } 25,000$ ($\$50–\$250$):** `REQUIRE_HUMAN_APPROVAL` (Mandatory human sign-off)
- **$>\text{INR } 25,000$ ($>\$250$):** `DENY` (Deterministic rejection)

### Profile: `support-v1`
- **$<\text{INR } 2,000$ ($<\$20$):** `ALLOW`
- **$\text{INR } 2,000–\text{INR } 10,000$ ($\$20–\$100$):** `REQUIRE_HUMAN_APPROVAL`
- **$>\text{INR } 10,000$ ($>\$100$):** `DENY`

### Profile: `sales-v1`
- **$\le 10\%$ Discount:** `ALLOW`
- **$11\%–30\%$ Discount:** `REQUIRE_HUMAN_APPROVAL` (VP Sales review)
- **$> 30\%$ Discount:** `DENY`

---

## 🧠 9. Persistent Memory Bank

Stored in **Google Cloud Firestore**, the Memory Bank preserves cross-session context for asynchronous workflows:
- `workflow_id`, `agent_id`, `session_id`, `state` (`INITIALIZED`, `RUNNING`, `PAUSED_FOR_APPROVAL`, `APPROVED`, `REJECTED`, `COMPLETED`, `FAILED`)
- `action_history`, `previous_decisions`, `tool_results`, `approval_record`
- Enables agents to pause mid-workflow and resume seamlessly when an operator signs off hours or days later.

---

## ⏳ 10. Long-Running Asynchronous Runtime & Crash Recovery

Built for distributed resilience against container restarts, network partitions, and duplicate deliveries:
- **Transactional Outbox & Idempotency Keys:** Unique keys (`gw:{workflow_id}:{action}:{target_id}`) prevent duplicate execution.
- **Processing Leases:** Tasks are leased for 60 seconds with atomic state claims.
- **Lease Expiration Recovery:** `recover_expired_leases()` automatically recovers tasks abandoned by crashed workers.
- **Exponential Retry Backoff:** Failed network dispatches back off exponentially (`10s * 2^(attempt-1)`).
- **Scenario 13 Race Guard:** Enforces `current_state == action.source_state` upon commit.

---

## 🛡️ 11. Model Safety Guardrail (Model Armor Concept)

Demarcation of defense layers:
1. **Layer 1: Model Safety / Prompt Defense:** Intercepts prompt injections, jailbreak patterns, and credential leaks before/after inference.
2. **Layer 2: Deterministic Action Validator:** 4-point verification (recipient, report ID, Decimal amounts, state machine legality).
3. **Layer 3: Corporate Policy Engine:** Domain restrictions and financial limits.
4. **Layer 4: Execution Governance:** ApprovalLoop Gateway.

---

## 📊 12. Observability & OpenTelemetry

ApprovalLoop instruments every lifecycle phase with OpenTelemetry-compliant spans:
- `gateway.authorize`, `identity.verify`, `model_safety.inspect`, `policy.evaluate`, `claim`, `gemini.draft`, `notification`, `state_transition`
- Sanitized attributes prevent secret or credential leaks into audit logs.
- Full trace inspection available live at `/api/traces` and runtime AgBOM at `/api/agbom`.

---

## 🎬 13. Critical Demo Scenarios (Key Hackathon Scenarios)

Demonstrate live in the dashboard (**http://127.0.0.1:8080**) or via terminal (`python evals/run_fleet_demo.py`):

| Scenario | Agent Request | Gateway Decision | Execution Flow |
| :--- | :--- | :--- | :--- |
| **Case A** | Finance Agent requests **Refund INR 2,000** ($20) | **`ALLOW`** | Identity Verified $\rightarrow$ Policy `< INR 5,000` $\rightarrow$ Automatic instant dispatch. |
| **Case B** | Finance Agent requests **Refund INR 20,000** ($200) | **`REQUIRE_HUMAN_APPROVAL`** | Identity Verified $\rightarrow$ Policy `INR 5,000–INR 25,000` $\rightarrow$ Workflow pauses in Memory Bank $\rightarrow$ Operator approves in Dashboard $\rightarrow$ Execution resumes. |
| **Case C** | Finance Agent requests **Refund INR 100,000** ($1,000) | **`DENY`** | Identity Verified $\rightarrow$ Policy `> INR 25,000` ceiling $\rightarrow$ Action blocked deterministically. **Gemini cannot override policy.** |

---

## 💻 14. Local Setup & Quickstart

### Prerequisites
- Python 3.10+
- Node.js 18+

### Quickstart Commands
```powershell
# 1. Activate environment
.\.venv\Scripts\Activate.ps1

# 2. (Optional) Set Gemini API Key
$env:GEMINI_API_KEY="your-gemini-api-key"
$env:GEMINI_MODEL="gemini-3.5-flash"

# 3. Start Backend & Dashboard (Port 8080)
python -m uvicorn approval_loop.api.app:app --host 127.0.0.1 --port 8080 --reload
```

Open **http://127.0.0.1:8080** in your browser.

---

## 🧪 15. Automated Test Suite (74 Tests Passing)

Run the full automated test suite:

```bash
pytest -v
```

```text
======================= 74 passed in 1.23s =======================
```

Test coverage includes:
- **Agent Registry:** Registration, retrieval, status toggling, capability checking
- **Agent Identity:** HMAC cryptographic signatures, OIDC verification, tampered token rejection, version checks
- **Agent Gateway:** ALLOW, REQUIRE_HUMAN_APPROVAL, DENY, human approval and rejection lifecycles
- **Memory Bank:** State persistence, session history, async pause and resumption
- **Async Runtime:** Leased task execution, idempotency deduplication, crash recovery
- **Model Safety Guardrails:** Prompt injection detection, credential leakage prevention
- **Deterministic State Machine & 4-Point Validator:** All legal transitions, amount precision, race guards
- **Production Health & Endpoints:** `/health/live`, `/health/ready`, `/healthz`, `/api/registry/...`
- **Critical Demo Scenarios:** Case A, Case B, and Case C end-to-end integration tests

---

## ☁️ 16. Google Cloud Infrastructure & Deployment

- **Gemini 3.5 Flash (`gemini-3.5-flash`):** Google GenAI SDK agent reasoning
- **Google Cloud Run:** Container hosting FastAPI backend and React Single-Page Application
- **Google Cloud Firestore:** Scalable ACID NoSQL datastore for Agent Registry, Memory Bank, and Outbox
- **Google Cloud Scheduler:** Managed serverless cron trigger (`*/1 * * * *`)
- **Google Secret Manager:** Secure injection of `GEMINI_API_KEY` and `AGENT_IDENTITY_SECRET`

Deploy to GCP with one command:
```bash
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
export GEMINI_API_KEY="your-gemini-api-key"
export GEMINI_MODEL="gemini-3.5-flash"

chmod +x deploy.sh
./deploy.sh
```

---

## ⚙️ 17. Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `demo` | Environment mode (`test`, `demo`, `production`) |
| `GEMINI_API_KEY` | *None* | Google Gemini API Key |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model version |
| `GOOGLE_CLOUD_PROJECT` | `approval-loop-hackathon` | Google Cloud Project ID |
| `USE_FIRESTORE` | `false` | Set `true` to use Firestore; `false` for in-memory |
| `SCHEDULER_API_KEY` | `dev-scheduler-secret-key` | Secret key for Cloud Scheduler trigger |
| `AGENT_IDENTITY_SECRET` | `fleet-identity-master-secret-key-2026` | Master key for HMAC agent tokens |
| `APP_ALLOWED_ORIGINS` | `http://localhost:5173,...` | Configured CORS origins (wildcards blocked in prod) |

---

## 🛡️ 18. Limitations & Honest Disclosure

1. **Notification Provider:** Defaults to `MockNotificationProvider` for safe local testing and demonstration without sending unsolicited emails. Production uses `ProductionNotificationProvider` with timeouts and retry classification.
2. **Local vs Cloud Storage:** Uses thread-safe locked dictionary memory repos in local demo mode; seamlessly connects to `FirestoreRepository` when `USE_FIRESTORE=true`.

---

## 🗺️ 19. Production Hardening Roadmap

- [x] Institutional Agent Fleet with Gemini 3.5 & Google GenAI SDK
- [x] Firestore-backed Agent Registry with capability whitelisting
- [x] Zero-trust cryptographic Agent Identity (HMAC & GCP OIDC)
- [x] ApprovalLoop Agent Gateway with versioned policy profiles
- [x] Human-in-the-Loop approval queue with workflow pause/resume
- [x] Persistent cross-session Memory Bank
- [x] Leased asynchronous task execution with crash recovery
- [x] Model Armor prompt defense guardrails
- [x] OpenTelemetry distributed tracing and AgBOM manifest
- [x] Production health endpoints (`/health/live`, `/health/ready`)
- [ ] Google Cloud Pub/Sub & Cloud Tasks managed distributed queue integration
- [ ] Google Cloud KMS key destruction hooks for enterprise key rotation
