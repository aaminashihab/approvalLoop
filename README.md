# ApprovalLoop — Fortified Enterprise Fleet Gateway

**ApprovalLoop is a secure control plane for autonomous enterprise agents: agents can reason and act asynchronously, while identity, safety, policy, approval, execution, memory, and observability remain centrally governed.**

> [!IMPORTANT]
> **Core Architectural Invariant**:
> **AI proposes. Deterministic policy decides. Infrastructure executes.**

ApprovalLoop bridges autonomous intelligence (**Google Gemini 3.5+**, **Google Agent Framework**) with deterministic corporate governance, zero-trust cryptographic identity, persistent memory banks, leased async execution, and mathematical safety gates.

---

## 1. The Problem

Autonomous AI agents are transitioning from conversational chatbots into institutional operators capable of taking real-world actions: issuing financial refunds, approving expenses, granting sales discounts, and updating ERP ledgers.

However, deploying autonomous agents directly to production tools creates existential enterprise risks:
1. **Direct Tool Authority:** When LLMs are equipped with direct tool-calling privileges, a single prompt injection, model hallucination, or ambiguous context can execute irreversible, unauthorized financial or state changes.
2. **Silent Workflow Stalls:** Stalled human approvals in enterprise systems silently halt operations because nobody prompts a conversational assistant when an approver is out of office.
3. **Session Amnesia:** Multi-step asynchronous workflows that require human sign-off lose context across disconnections or container restarts.
4. **Duplicate Execution:** Network timeouts and overlapping scheduler invocations cause duplicate side-effect execution.

---

## 2. Why Autonomous Agents Need Execution Governance

Non-deterministic models are brilliant at reasoning, context comprehension, and proposal formulation. They must **never** hold authoritative authorization over money, database state, or external side effects.

ApprovalLoop enforces an absolute separation of concerns:

| Responsibility | Component | Implementation |
| :--- | :--- | :--- |
| **Reasoning & Proposals** | **Gemini Agent Fleet** | Gemini 3.5 via Google GenAI SDK (`google-genai`) emits structured `AgentActionProposal` |
| **Identity & Authentication** | **Agent Identity Layer** | HMAC-SHA256 & Google Cloud IAM OIDC zero-trust token verification with replay protection |
| **Inline Safety Layer** | **Google Cloud Model Armor** | Official Google Cloud Model Armor API (`google-cloud-modelarmor`) inspecting pre-LLM prompts (`SanitizeUserPrompt`) and post-LLM responses (`SanitizeModelResponse`) |
| **Parameter Integrity** | **4-Point Safety Validator** | Deterministic mathematical checks (exact Decimal precision, ID matching) |
| **Authorization Policy** | **Policy Engine** | Versioned deterministic profiles (`finance-v3`, `support-v1`, `sales-v1`) |
| **Execution Governance** | **Agent Gateway** | Emits `ALLOW`, `REQUIRE_HUMAN_APPROVAL`, or `DENY` decisions |
| **Persistent Context** | **Memory Bank** | Firestore-backed cross-session state, action history, and pause/resume capability |
| **Asynchronous Execution** | **Async Runtime & Workers** | Leased task execution with crash recovery, retry backoff, and idempotency keys |
| **Audit & Observability** | **OpenTelemetry** | Distributed traces and audit ledger reconstructing full causality with correlation IDs |

---

## 3. Architecture & Control Plane Flow

```text
                                              AGENT
                                                │
                                                ▼
                                    GOOGLE CLOUD MODEL ARMOR
                               (Pre-LLM: SanitizeUserPrompt API)
                                                │
                                                ▼
                                             GEMINI
                                 (Google GenAI SDK - Gemini 3.5)
                                                │
                                                ▼
                                    GOOGLE CLOUD MODEL ARMOR
                              (Post-LLM: SanitizeModelResponse API)
                                                │
                                                ▼
                                          AGENT GATEWAY
                                      (ApprovalLoop Control Plane)
                                                │
                                                ▼
                                          POLICY ENGINE
                               (Deterministic Profiles: finance-v3)
                                                │
                                                ▼
                                          ASYNC RUNTIME
                                    (Leased Async Execution)
                                                │
                                                ▼
                                     TOOL / ENTERPRISE ACTION
                                                 │
                                                 ▼
                                            MEMORY UPDATE
                                       (Persistent Memory Bank)
                                                 │
                                                 ▼
                                       AUDIT & OPENTELEMETRY
```

---

## 4. Gemini Agent Fleet

ApprovalLoop orchestrates a scalable network of specialized institutional agents built on the **Google Agent Framework (Google GenAI SDK `google-genai`)** with **Gemini 3.5 Flash**:

1. **Finance Agent (`finance-agent` v1.2.0):** Evaluates corporate refund claims, invoice anomalies, and stalled expense approvals. Formulates structured proposals (`issue_refund`, `approve_expense`, `escalate_stalled_approval`).
2. **Support Agent (`support-agent` v1.1.0):** Evaluates customer SLA disputes and service outages. Formulates structured compensation proposals (`credit_account`, `escalate_ticket`, `sla_override`).
3. **Sales Agent (`sales-agent` v1.0.0):** Evaluates enterprise contract terms and ARR margins. Formulates structured commercial discount proposals (`grant_discount`, `waive_fee`, `custom_contract_terms`).

**Zero Direct Tool Access:** Fleet agents have **zero** direct network access to databases or payment APIs. Every proposed action is emitted as a strictly typed Pydantic `AgentActionProposal` and submitted to the Gateway.

---

## 5. Agent Registry & Identity

Persistent in **Google Cloud Firestore**, the Agent Registry defines the identity, capabilities, and boundaries of every registered agent:
- `agent_id`: Unique identifier (e.g. `finance-agent`)
- `name`: Human-readable agent title
- `description`: Role and functional boundary
- `version`: Running semver (e.g. `1.2.0`)
- `owner`: Operational owner email
- `status`: `ACTIVE`, `DISABLED`, `DEPRECATED`
- `capabilities`: Registered cognitive capabilities
- `allowed_tools`: Authorized tool list
- `allowed_actions`: Authorized action whitelist
- `policy_profile`: Applied policy profile (`finance-v3`)
- `risk_level`: Assigned risk classification (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)

**Zero-Trust Identity Enforcement:**
- HMAC-SHA256 token verification with timestamp window & request_id replay protection.
- Google Cloud IAM OIDC token verification hook.
- Strict agent status & `allowed_actions` whitelist checks before any proposal reaches policy evaluation.

---

## 6. Model Armor-Inspired Deterministic Safety Guardrail

The `ModelSafetyGuardrail` operates before and after LLM inference as a deterministic defense layer:
- **Prompt Injection Defense:** Intercepts instruction overrides (`ignore prior rules`, `DAN mode`, `developer mode`, `system override`).
- **Tool Poisoning & Command Injection:** Rejects malicious payloads (`drop table`, `rm -rf`, `eval()`, `exec()`, `curl | sh`, `system()`).
- **Credential Leakage Prevention:** Scans inputs and outputs for API keys and secrets (Google API keys, AWS keys, GitHub tokens, Slack tokens, JWTs, private keys).
- **Script & HTML Injection:** Filters `<script>`, `javascript:`, `onload=` payloads.

---

## 7. Deterministic Policy Engine

Policy decisions are 100% deterministic, immutable, and reproducible:
- **Unknown Profile Fail-Closed:** Unknown policy profiles are rejected immediately.
- **Currency & Amount Enforcement:** Supported currencies (`USD`, `INR`) are validated; negative amounts rejected. Exact `Decimal` arithmetic is preserved throughout.

### Policy Profile: `finance-v3`
- **$<\text{INR } 5,000$ ($<\$50$):** `ALLOW` (Autonomous Execution)
- **$\text{INR } 5,000–\text{INR } 25,000$ ($\$50–\$250$):** `REQUIRE_HUMAN_APPROVAL` (Mandatory Human Sign-Off)
- **$>\text{INR } 25,000$ ($>\$250$):** `DENY` (Deterministic Rejection)

---

## 8. Durable Async Runtime & Persistent Memory Bank

- **Firestore Memory Bank:** Stores workflow state, session IDs, action history, previous decisions, and approval records across restarts.
- **Durable Task Leasing:** `AsyncAgentRuntime` persists task records (`async_tasks` collection in Firestore), managing lease acquisition, lease expiry, exponential retry backoff, and crash recovery. Tasks do not disappear when Cloud Run restarts.
- **Single-Claim Approval Transitions:** Atomic transitions guarantee concurrent approval requests result in exactly one successful execution.

---

## 9. Observability & OpenTelemetry

- **Correlated Spans:** Traces span across `observe` -> `eligibility` -> `skill.load` -> `claim` -> `gemini.draft` -> `validation` -> `policy.check` -> `notification` -> `state_transition`.
- **Correlation IDs:** `trace_id`, `proposal_id`, `workflow_id`, `task_id` propagate across all steps.
- **Secret Redaction:** Attributes containing `key`, `secret`, `password`, `token`, `auth` are automatically redacted.

---

## 10. Killer Demo Workflow

**Stale Expense Approval (Case B)**:
1. An expense approval has been pending for 48 hours.
2. Background trigger fires (Cloud Scheduler / API tick).
3. Agent wakes autonomously and reads persistent Memory Bank context.
4. Gemini analyzes the situation and drafts a structured escalation proposal.
5. Agent Gateway verifies identity (HMAC/OIDC).
6. Safety layer checks input/output (Deterministic Model Safety Guardrail).
7. Policy evaluates risk: refund amount ₹20,000 ($200) falls in the medium-risk tier (`REQUIRE_HUMAN_APPROVAL`).
8. Workflow pauses durably in Memory Bank.
9. Human Approval Queue displays the pending decision.
10. Operator approves via UI/API.
11. Async worker resumes, executes action, updates memory, and emits full OpenTelemetry trace.

---

## 11. Implemented vs Roadmap

### IMPLEMENTED & VERIFIED
- [x] Autonomous Agent wake-up & Gemini 3.5 reasoning
- [x] Gemini structured proposal generation via Pydantic
- [x] Agent Registry with status, capabilities & allowed actions
- [x] Zero-Trust Identity Provider (HMAC-SHA256 + GCP OIDC + Replay Protection)
- [x] Custom Deterministic Model-Safety Guardrail (prompt defense & secret leakage filter)
- [x] Deterministic Policy Engine (`finance-v3`, `support-v1`, `sales-v1`)
- [x] Human-in-the-Loop Approval Queue & durable workflow pause/resume
- [x] Durable Async Runtime with Firestore task leasing & crash recovery
- [x] Distributed Replay Protection with Firestore-backed request ID deduplication
- [x] Persistent Memory Bank (Firestore & In-Memory with atomic transactions)
- [x] OpenTelemetry correlated distributed tracing & Observability ("Why did ApprovalLoop act?")
- [x] Real Notification Providers (Slack Webhook & SMTP Email adapters)
- [x] 3-Tier Demo Scenarios (Case A ALLOW, Case B HUMAN APPROVAL, Case C DENY)
- [x] Google Cloud Run & Cloud Scheduler deployment automation
- [x] 100% Clean test suite (114 passing backend unit/integration tests)

### OPTIONAL / FUTURE ROADMAP
- [ ] Direct Google Cloud Pub/Sub integration for sub-second event streaming
- [ ] Multi-region active-active Firestore replication
- [ ] Enterprise SSO (Okta / Azure AD SAML) integration

---

## 12. Local Setup & Testing

### Prerequisites
- Python 3.10+
- Node.js 20+

### Step 1: Clone & Setup Virtual Environment
```bash
git clone https://github.com/aaminashihab/approvalLoop.git
cd approvalLoop
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r backend/requirements.txt
```

### Step 2: Environment Variables
Create a `.env` file or export:
```bash
APP_ENV=demo
GOOGLE_CLOUD_PROJECT=approval-loop-hackathon
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
SCHEDULER_API_KEY=dev-scheduler-secret-key
AGENT_IDENTITY_SECRET=fleet-identity-master-secret-key-2026
ALLOW_INSECURE_DEMO_AUTH=false
```

### Step 3: Run Tests
```bash
# Run full pytest suite (114 tests)
$env:PYTHONPATH="backend"
python -m pytest backend/tests -v
```

### Step 4: Run Backend & Frontend Locally
```bash
# Terminal 1: Backend API
python -m uvicorn approval_loop.api.app:app --host 0.0.0.0 --port 8080 --reload

# Terminal 2: Frontend Dev Server
cd frontend
npm install
npm run dev
```

---

## 13. Google Cloud Deployment

Deploy ApprovalLoop to **Google Cloud Run** with **Cloud Scheduler** and **Firestore**:

```bash
# Set Google Cloud credentials & project
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
export GEMINI_API_KEY="your-gemini-api-key"
export REGION="us-central1"
export APP_ENV="demo"

# Execute automated deployment script
chmod +x deploy.sh
./deploy.sh
```

---

## 14. License

Licensed under the [Apache License 2.0](LICENSE).
