#  ApprovalLoop

**ApprovalLoop is an autonomous AI agent that monitors stalled expense approvals and takes bounded, validated action without waiting for a human prompt.**

---

##  Problem

Modern enterprise operations silently grind to a halt because **approvals stall in human inboxes**.

An employee submits an expense report, access request, or vendor invoice. The designated approver travels, gets overwhelmed with meetings, or forgets. Nobody prompts an AI chatbot because nobody is watching the clock. The workflow silently stalls, deadlines pass, and business velocity is lost.

---

##  Solution

**ApprovalLoop** is an unprompted autonomous follow-up agent that monitors workflow health and acts on stalled human tasks.

Driven by a background schedule (**Google Cloud Scheduler**), ApprovalLoop wakes up periodically, observes pending approval states, determines when an approval has become stale, calls **Gemini 3.5 Flash** to draft polite, contextual reminders, verifies every parameter against strict deterministic code invariants, checks corporate governance policy, claims the action atomically, dispatches notifications, and conditionally updates business state.

---

##  Why This Is an Autonomous Agent (Not a Chatbot)

Unlike conversational assistants that wait for user prompts:

1. **Runs Asynchronously:** Executes in the background without human presence.
2. **Wakes on Schedule:** Google Cloud Scheduler triggers execution cycles autonomously (`*/1 * * * *`).
3. **Evaluates State:** Scans open approvals and evaluates elapsed time against immutable thresholds.
4. **Plans & Drafts:** Decides required interventions (*Nudge* vs *Escalate*) and drafts contextual communication using Gemini 3.5 Flash with structured output validation.
5. **Validates Before Action:** Enforces a strict 4-point deterministic safety validator gate.
6. **Authorizes via Policy:** Evaluates corporate governance rules (domain whitelist, financial limits, environment guards).
7. **Executes Bounded Action:** Dispatches notification payloads through a deterministic simulated worker with delivery receipt logging.
8. **Continuous Lifecycle:** Persists audit records, records OpenTelemetry-compatible traces, sleeps, and repeats the loop indefinitely.

---

##  Core Architecture Principle: *“LLM proposes. Code disposes.”*

In autonomous financial and operational systems, non-deterministic models must **never** hold authoritative power over state changes, money, or recipients.

| Decision / Property | Handled By | Safety Guarantee |
| :--- | :--- | :--- |
| **Workflow State Machine** | Deterministic Code | Strict transitions (`Pending → Nudged → Escalated → Resolved`) |
| **Monetary Values** | Python `Decimal` | Exact precision, zero floating-point drift |
| **Elapsed Time & Stale Rules** | Deterministic Code | Evaluated on immutable timestamps against strict thresholds |
| **Approver Hierarchy** | Approver Registry | Resolves primary, backup, and fail-closed corporate admin |
| **Contextual Communication** | **Gemini 3.5 Flash (Google GenAI SDK)** | Polite, situation-aware structured language drafting |
| **Safety Gate** | **4-Point Deterministic Validator** | Intercepts & blocks any recipient, amount, report ID, or state mismatch |
| **Governance Authorization** | **Corporate Policy Engine** | Enforces domain restrictions, high-value financial rules, and env guards |
| **Concurrency & Idempotency** | **Transactional Outbox Claim** | Atomic claim before drafting (`{report_id}:{action_type}`) |
| **Race-Condition Safety** | **Conditional Transition Guard** | Enforces `current_state == action.source_state` |

---

##  Autonomous Workflow & Architecture

<p align="center">
  <img src="docs/architecture_diagram.svg" alt="ApprovalLoop Software Architecture Diagram" width="100%" />
</p>

<p align="center">
  <a href="docs/architecture_diagram.html">🔍 <b>Open Interactive Pan/Zoom Diagram</b></a> • 
  <a href="docs/ARCHITECTURE.md">📖 <b>Read Complete Architecture Blueprint</b></a>
</p>

```mermaid
flowchart TD
    subgraph GCP["Google Cloud Platform"]
        CS["Google Cloud Scheduler<br/>Cron: */1 * * * *"] -->|HTTP POST /api/tick| CR["Google Cloud Run<br/>FastAPI Backend"]
        CR -->|Read / Write State| FS[("Google Cloud Firestore<br/>State &amp; Outbox")]
    end

    subgraph Engine["ApprovalEngine Orchestrator"]
        CR --> OBS["1. Observe Open Approvals"]
        OBS --> DEC["2. Decide Eligibility &amp; Action"]
        DEC --> SKL["3. Runtime Skill Discovery<br/>Progressive Disclosure Loader"]
        SKL --> CLM["4. Atomic Outbox Claim<br/>Key: report_id:action_type"]
        
        CLM -->|Transactional Lock Granted| GAI["5. Google GenAI SDK<br/>Gemini 3.5 Flash Drafter"]
        GAI --> DRAFT["Structured Draft Proposal<br/>Pydantic Schema Validated"]
        
        DRAFT --> VAL{"6. 4-Point Deterministic<br/>Safety Validator"}
        VAL -->|PASS| POL{"7. Corporate Policy Engine<br/>Domain &amp; Limit Authorization"}
        VAL -->|FAIL / BLOCKED| BLK["Blocked &amp; Audited<br/>Dispatch Aborted"]
        
        POL -->|ALLOW| ACT["8. Notification Worker<br/>Dispatch Simulation &amp; Logging"]
        POL -->|DENY| BLK
        
        ACT --> CG{"9. Conditional State Guard<br/>current == source_state"}
        CG -->|MATCH| APP["State Applied<br/>Pending -&gt; Nudged"]
        CG -->|MISMATCH / Resolved| SKP["State Skipped<br/>Resolved Preserved"]
        
        APP --> AUD[("Audit Ledger &amp; OTel Traces")]
        SKP --> AUD
        BLK --> AUD
    end
```

---

##  Safety & Reliability Architecture

ApprovalLoop implements a **4-Point Deterministic Safety Validator + Corporate Policy Engine + Transactional Idempotency Gate**:

```
[Candidate Action]
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ 1. Transactional Idempotency Gate                      │
│ Atomic claim on `{report_id}:{action_type}` in DB       │
└──────────────────────┬─────────────────────────────────┘
                       │ Claim Granted
                       ▼
┌────────────────────────────────────────────────────────┐
│ 2. Gemini 3.5 Flash Drafter (Language Wording Only)    │
│ Strict Pydantic DraftProposalResponse validation       │
└──────────────────────┬─────────────────────────────────┘
                       │ Structured Proposal
                       ▼
┌────────────────────────────────────────────────────────┐
│ 3. 4-Point Deterministic Safety Validator              │
│ - Recipient Verified (Authoritative Registry Check)   │
│ - Report ID Verified (Matches Authoritative Record)    │
│ - Amount Verified (Exact Decimal Match)                │
│ - State Verified (Legal State Machine Transition)      │
└──────────────────────┬─────────────────────────────────┘
                       │
                       ▼ PASS
┌────────────────────────────────────────────────────────┐
│ 4. Corporate Policy Engine                             │
│ - Domain Whitelist / Anti-Spoofing Policy             │
│ - High-Value Financial Escalation Policy (≥ $5,000)   │
│ - Production Environment Safety Guards                 │
└──────────────────────┬─────────────────────────────────┘
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
           ALLOW               DENIED / BLOCKED
```

1. **Deterministic State Machine:** Restricts transitions strictly to legal paths (`Pending → Nudged → Escalated`, terminal `Resolved`). Direct jumps or reverts are blocked.
2. **Transactional Outbox Claim:** Actions are atomically claimed before invoking Gemini, preventing duplicate runs and wasted LLM tokens during concurrent ticks.
3. **Scenario 13 Race-Condition Guard:** If an approver resolves a report while a notification is in transit, the commit guard verifies `current_state == action.source_state`. If the report was resolved, the transition is recorded as **`SKIPPED`** and the `Resolved` state is preserved.
4. **Deterministic Notification Worker:** The notification dispatch engine models the complete delivery lifecycle, logging unique message IDs, tracking receipt timestamps, and testing provider-side deduplication without sending unsolicited emails from test environments.
5. **OpenTelemetry-Compatible Execution Tracing:** End-to-end spans (`approval.tick`, `observe`, `eligibility`, `claim`, `gemini.draft`, `validation`, `policy.check`, `notification`, `state_transition`) are recorded for observability without logging sensitive credentials.
6. **Agent Bill of Materials (AgBOM):** Declared runtime dependency and safety inventory of models, frameworks, datastores, tools, and safety layers exposed at `/api/agbom`.
7. **Agent Skill:** Reusable procedural knowledge defined in [`skills/approval_escalation/SKILL.md`](file:///d:/hackathon/skills/approval_escalation/SKILL.md) loaded dynamically at runtime via `SkillRegistry` using progressive disclosure.

---

##  Google Cloud Proof & Technologies

- **Gemini 3.5 Flash (`gemini-3.5-flash`):** Default model for contextual language generation.
- **Google Agent Framework (Google GenAI SDK `google-genai`):** Official Python SDK for invoking Gemini models.
- **Google Cloud Run:** Serverless container hosting the FastAPI backend and React Single-Page Application.
- **Google Cloud Firestore:** Scalable NoSQL database with transactional outbox and state storage.
- **Google Cloud Scheduler:** Managed serverless cron service triggering autonomous execution cycles (`*/1 * * * *`).

---

##  Local Setup & Quickstart

### 1. Prerequisites
- Python 3.10+
- Node.js 18+

### 2. Installation
```powershell
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Set Gemini API key (optional for offline fallback, recommended for live LLM)
$env:GEMINI_API_KEY="your-gemini-api-key"
$env:GEMINI_MODEL="gemini-3.5-flash"

# 3. Start the application (FastAPI + React Dashboard on port 8080)
python -m uvicorn approval_loop.api.app:app --host 127.0.0.1 --port 8080 --reload
```

Open **http://127.0.0.1:8080** in your browser.

---

##  Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `demo` | Environment mode (`test`, `demo`, `production`) |
| `GEMINI_API_KEY` | *None* | Google Gemini API Key (injected via environment or Secret Manager) |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model version (`gemini-3.5-flash`) |
| `GOOGLE_CLOUD_PROJECT` | `approval-loop-hackathon` | Google Cloud Project ID |
| `USE_FIRESTORE` | `false` | Set `true` to use Google Cloud Firestore; `false` for in-memory |
| `SCHEDULER_API_KEY` | `dev-scheduler-secret-key` | Secret key for authenticating Cloud Scheduler calls |
| `ADMIN_FALLBACK_EMAIL` | `escalations-owner@company.internal` | Fallback escalation address when no backup approver exists |

---

##  Google Cloud Deployment

Deploy with one command using the provided script:

```bash
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
export GEMINI_API_KEY="your-gemini-api-key"
export GEMINI_MODEL="gemini-3.5-flash"

chmod +x deploy.sh
./deploy.sh
```

---

##  Automated Testing (47 Tests Passing)

Run the full automated test suite:

```bash
pytest -v
```

```text
============================= 47 passed in 2.80s ==============================
```

Test coverage includes:
- **Deterministic State Machine:** All legal transitions and illegal jump rejection
- **4-Point Safety Validator:** Recipient, Report ID, Decimal amount, and State validation
- **Corporate Policy Engine:** Domain restrictions, high-value director threshold ($\ge \$5,000$), state invariants, and environment guards
- **Transactional Outbox Claim:** Atomic idempotency and race deduplication
- **Notification Provider Hierarchy:** Mock simulator with latency/fault injection and Production adapter
- **Gemini Structured Output:** Tone and reasoning validation, markdown fence stripping, and resilient offline templates
- **OpenTelemetry Tracer:** Span lifecycle and credential sanitization
- **1,000-Report Scale Simulation:** 1,000 concurrent synthetic approval lifecycles evaluated in <0.1s with 0 duplicate sends and 0 unsafe transitions

---


## 🛡️ Limitations & Honest Disclosure

- **Notification Provider:** For hackathon demonstration and testing safety, the system defaults to `MockNotificationProvider`, simulating provider idempotency, receipt tracking, and network fault injection without sending unsolicited emails to real mailboxes. The architecture uses a clean `BaseNotificationProvider` abstraction so that an enterprise provider (e.g. SendGrid, Google Cloud Tasks, or Corporate SMTP) can be substituted in production without altering agent orchestration logic.
- **Transactional Firestore:** In local test suites, `InMemoryRepository` provides thread-safe dictionary storage with lock synchronization; in cloud deployment, `FirestoreRepository` provides ACID document transactions.

---



