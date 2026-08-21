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

Persistent in **Google Cloud Firestore**, the Agent Registry defines the identity, capabilities, and boundaries of every ## 🔐 6. Agent Identity & Zero-Trust Access Control

Requests to the Gateway require authenticated cryptographic identity rather than trusting arbitrary headers:
- **Cryptographic JWT / OIDC Verification:** Fails closed if token signature, issuer, or audience verification fails. Unverified JWT payloads are **never** decoded or trusted.
- **HMAC-SHA256 Token Provider:** Cryptographically signs and verifies agent requests with timestamp-based replay attack mitigation.
- **Google Cloud IAM OIDC Verification:** Verifies Google Cloud Service Account identity tokens in production with strict cryptographic verification.
- **Authenticated Human Operator Approvals:** Human approval/rejection endpoints require authenticated operator identity derived strictly from verified credentials (`X-API-Key` or OIDC token). Client-supplied request body names are ignored for identity.
- **Durable & Transactional Approval Transitions:** Pending approvals are stored durably in Memory Bank (surviving container/process restarts) and support atomic single-claim transitions preventing duplicate executions.
- **Verification Invariants:**
  1. Cryptographic token signature is valid and unexpired.
  2. Agent exists in Registry and status is `ACTIVE`.
  3. Running agent version matches registered specification.
  4. Requested action is explicitly in the agent's `allowed_actions` whitelist.

---

## 📜 8. Deterministic Policy Engine with Versioned Profiles

Policy decisions are 100% deterministic, immutable, and reproducible from structured input:
- **Unknown Profile Fail-Closed:** Unknown policy profiles are rejected immediately (`[UNKNOWN_POLICY_PROFILE]`). Default profile fallbacks are prohibited.
- **Currency & Amount Enforcement:** Only explicitly supported currencies (`USD`, `INR`) are accepted. Unsupported currencies (`EUR`, `GBP`, `AED`) and negative amounts are rejected immediately (`[UNSUPPORTED_CURRENCY]`, `[INVALID_AMOUNT]`). Exact `Decimal` arithmetic is preserved throughout.

### Profile: `finance-v3`
- **$<\text{INR } 5,000$ ($<\$50$):** `ALLOW` (Automatic execution)
- **$\text{INR } 5,000–\text{INR } 25,000$ ($\$50–\$250$):** `REQUIRE_HUMAN_APPROVAL` (Mandatory human sign-off)
- **$>\text{INR } 25,000$ ($>\$250$):** `DENY` (Deterministic rejection)

---

## 🧪 15. Automated Test Suite

Run the full automated test suite:

```bash
pip install -r backend/requirements.txt
pytest -v
```

Test coverage includes:
- **Cryptographic JWT / OIDC Auth:** Valid token acceptance, forged/unverified signature rejection (fails closed), expired token rejection, issuer/audience validation
- **Human Approval Security & Concurrency:** Authenticated operator sign-offs, request body operator identity override prevention, atomic double-approval prevention, durable state recovery
- **Agent Registry & Identity:** Registration, retrieval, status toggling, capability whitelist enforcement, agent ID & version binding
- **Policy Hardening:** Unknown profile fail-closed rejection, unsupported currency rejection (`EUR`, `GBP`, `AED`), invalid/negative amount rejection, exact Decimal arithmetic
- **Demo Mode Safety:** Explicit opt-in `ALLOW_INSECURE_DEMO_AUTH` enforcement, production startup safety validation (fails closed if demo auth is enabled in production)
- **Async Runtime & Outbox:** Leased task execution, idempotency deduplication, crash recovery, exponential backoff
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
