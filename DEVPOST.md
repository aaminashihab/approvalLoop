# ApprovalLoop — Devpost Submission Information

## 🏷️ Basic Project Information

- **Project Title:** ApprovalLoop
- **Elevator Pitch:** An autonomous, unprompted AI agent that monitors stalled expense approvals and takes bounded, validated action using Gemini 3.5 Flash and Google Cloud serverless infrastructure.
- **Track:** Taskmaster

---

## 💡 Inspiration

In enterprise workflows, the single largest cause of operational drag isn't complex decisions—it's **human inaction**. An expense report, purchase order, or IT access request is submitted, but the designated approver travels or gets overwhelmed with meetings. 

Nobody prompts an AI chatbot because nobody is watching the clock.

We asked: *Why should agents wait for a user prompt when the clock itself is an authoritative trigger?*

**ApprovalLoop** was built on the thesis:
> **“Most agents wait for a prompt. ApprovalLoop acts when nothing happens.”**

---

## ⚙️ What It Does

ApprovalLoop runs in the background on Google Cloud without human intervention:
1. **Wakes Autonomously:** Triggered on schedule by Google Cloud Scheduler (`*/1 * * * *`) without human presence.
2. **Observes Workflow State:** Scans open expense approvals stored in Firestore.
3. **Decides Bounded Action:** Evaluates elapsed time against corporate thresholds (*Pending > 30s $\rightarrow$ Nudge; Nudged > 90s $\rightarrow$ Escalate* in demo).
4. **Discovers Procedural Skills:** Loads the `approval_escalation` skill at runtime via progressive disclosure.
5. **Claims Action Atomically:** Uses a transactional outbox key (`{report_id}:{action_type}`) to prevent duplicate sends across concurrent workers.
6. **Drafts Contextual Language:** Prompts **Google Gemini 3.5 Flash** via the **Google GenAI SDK** to generate polite, situation-aware reminders with strict structured output validation.
7. **Enforces Deterministic Safety:** Runs a **4-Point Deterministic Safety Validator** (*Recipient, Report ID, Amount, Legal State*).
8. **Authorizes via Corporate Policy:** Enforces domain governance and high-value financial limits ($\ge \$5,000$).
9. **Dispatches Notifications:** Executes notification dispatch via a tracked deterministic simulated worker with delivery receipt logging.
10. **Guards Against Race Conditions:** Uses conditional state transitions (`current_state == action.source_state`) so that manual human sign-offs mid-flight are never overwritten.
11. **Emits Observability Traces:** Generates OpenTelemetry-compatible traces and maintains a declared runtime dependency and safety inventory (AgBOM).

---

## 🏛️ How We Built It (Architecture & Tech Stack)

- **AI Model:** Google Gemini 3.5 Flash (`gemini-3.5-flash`)
- **Agent Framework:** Google GenAI SDK (`google-genai` Python library)
- **Agent Skill:** Reusable progressive-disclosure skill in `skills/approval_escalation/` loaded by `SkillRegistry`
- **Backend Service:** FastAPI + Python 3.10 with strict Pydantic, `Decimal` financial precision, and OpenTelemetry-compatible execution tracing
- **Frontend Dashboard:** React 18 + TypeScript + Vite + Tailwind CSS + Lucide Icons (Pure observational dashboard)
- **Cloud Infrastructure:**
  - **Google Cloud Run:** Fully managed serverless container host
  - **Google Cloud Scheduler:** Managed cron trigger waking the autonomous agent loop
  - **Google Cloud Firestore:** Scalable NoSQL database with transactional outbox and state machine records

---

## 🛡️ Core Architectural Principle: *“LLM proposes. Code disposes.”*

In autonomous operations, language models must **never** hold authoritative power over state changes, money, or recipients.
- **Gemini 3.5 Flash** is strictly confined to natural language drafting.
- **Deterministic Python Code & Policy Engine** own eligibility, amounts, recipient authorization, state transitions, and audit logs.

---

## 📊 Scale Benchmark & Verification

- **47 Automated Pytest Tests Passing (100%)**
- **1,000-Report Deterministic Scale Benchmark:**
  - Evaluated 1,000 concurrent synthetic approval lifecycles in 0.08 seconds.
  - **Duplicate Actions on Repeated Ticks:** `0` (100% Idempotent)
  - **Invalid State Transitions:** `0` (100% Legal)
  - **Unauthorized External Sends:** `0` (100% Blocked)
  - **Human Prompts Required for Autonomous Loop:** `0` (100% Unprompted Autonomy)


---

## 💡 What We Learned

1. **Autonomous Time Triggers > Conversational Prompting:** The highest leverage for agentic systems is operating when no human is around.
2. **The "LLM Proposes, Code Disposes" Boundary:** Strict separation between language generation and deterministic authorization is essential for enterprise production readiness.
3. **Race Conditions are First-Class Concerns:** Distributed workflows must account for human sign-offs occurring while autonomous notifications are in transit.
4. **AgBOM & Observability:** Real-time execution tracing and declared runtime manifests give enterprises full visibility into agent behavior.
