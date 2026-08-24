# ApprovalLoop — Implementation Task

You are implementing an existing hackathon project called **ApprovalLoop**.

## IMPORTANT: Read Before Changing Anything

Before writing or modifying code:

1. Inspect the entire repository structure.
2. Read these project documents if present:
   - `SPEC.md`
   - `ARCHITECTURE.md`
   - `TEST_SCENARIOS.md`
   - `DEMO_SCRIPT.md`
   - existing README
3. Inspect the existing implementation, tests, configuration, and deployment files.
4. Identify what is already implemented versus missing.
5. Do NOT redesign the architecture unless there is a concrete implementation contradiction with the frozen architecture.

The architecture is **FROZEN**. Your job is to implement it faithfully.

---

# Product

ApprovalLoop is an autonomous expense-report approval chasing agent.

Thesis:

> "Most agents wait for a prompt. ApprovalLoop acts when nothing happens."

The system watches expense reports on a schedule. It detects stale approvals using deterministic time-based rules, asks Gemini only to draft the notification wording, validates that wording deterministically, sends the notification, and records the resulting state transition and audit trail.

The workflow is intentionally narrow: **Expense report approval chasing only.**
Do not turn this into a generic approval platform.

---

# NON-NEGOTIABLE ARCHITECTURAL PRINCIPLE

## LLM proposes, code disposes.

Gemini is allowed to decide: wording, tone, how to communicate the already-determined action.

Gemini is NOT allowed to decide: whether an action is due, the authoritative report state, whether a transition is legal, the recipient identity, the authoritative amount, the report ID, whether a notification is allowed to be sent, whether a resolved report should be touched.

Deterministic code owns those decisions.

The pipeline must remain:

```
Cloud Scheduler
      |
Check reports
      |
Firestore state + current time
      |
Deterministic eligibility calculation
      |
LEGAL ACTION determined by code
      |
Gemini drafts wording
      |
Firestore claim transaction
      |
Notification worker
      |
Deterministic validator
      |
PASS -----------> SEND
BLOCK -----------> AUDIT ONLY
      |
Conditional business-state transition
      |
Firestore audit record
```

Do not allow Gemini to return an authoritative state and have the application trust it.

---

# State Machine

The only business states are: `Pending`, `Nudged`, `Escalated`, `Resolved`.

Legal transitions:

```
Pending  --[nudge threshold elapsed]-->  Nudged
Nudged   --[escalation threshold elapsed since last_nudged_at]-->  Escalated
Pending/Nudged/Escalated --[approver acts]--> Resolved
Resolved --[any scheduler tick]--> Resolved
```

`Resolved` is terminal. The LLM must never determine these transitions.

---

# Deterministic Eligibility

Implement eligibility entirely in code.

Nudge: `current_time - submitted_at >= nudge_threshold AND status == Pending`
Escalation: `current_time - last_nudged_at >= escalation_threshold AND status == Nudged`

Never ask Gemini whether something is "stale." The scheduler only triggers a
check; eligibility code determines whether an action is actually due.

---

# Threshold Configuration

Thresholds MUST be configuration-driven, never hardcoded in business logic.

```
TEST:        nudge = 2s,  escalation = 5s
DEMO:        nudge = 30s, escalation = 90s
PRODUCTION (documented): nudge = 24h, escalation = 72h
```

Scheduler frequency is a separate config value from these thresholds. For demo
deployment: `scheduler frequency = 15-30 seconds`. The scheduler remains the
real trigger — never a fake timer or manual trigger.

---

# Firestore

Use Firestore as the source of truth. Reports contain at minimum: `report_id`,
`status`, `submitted_at`, `approver`, `backup_approver`, `amount`,
`last_nudged_at`, `escalated_at`. Use proper timestamp types, not strings.

---

# Logical Idempotency

The idempotency key identifies the logical action, not a scheduler attempt:

```
{report_id}:nudge
{report_id}:escalate
```

Do NOT use `{report_id}:{action_type}:{tick_id}` as the dedup key. `tick_id`
may exist separately for observability. A failed send retries the same logical
action (`EXP-104:nudge: failed -> retry -> sent`) — never creates
`EXP-104:nudge-2`.

---

# Firestore Claim Transaction

No external network side effects inside the transaction. Inside it: re-read
the report, verify current state, verify eligibility, verify the logical
action hasn't already been claimed, create the action record, commit. Never
send Slack/email inside this transaction — retries must never cause duplicate
external sends.

---

# Action Record

```
action_id, report_id, action_type, source_state, target_state, tick_id,
idempotency_key, recipient, amount, created_at, validator_result,
validator_reason, message, sent_at, status, state_transition, skip_reason, error
```

Valid `action_type`: nudge | escalate. `validator_result`: pass | blocked.
`status`: claimed | sent | failed | blocked. `state_transition`: applied | skipped.
Every action must produce an audit record, including blocked actions.

---

# Gemini

Use the existing Gemini/ADK implementation if one exists. Gemini receives a
deterministic instruction such as `"Action required: NUDGE report EXP-104."`
and produces only the notification content. It must never determine state,
recipient, amount, report_id, legal transition, or eligibility. Prefer
structured output/Pydantic validation for the model response — but schema
validation is not a substitute for the deterministic business validator.

---

# Deterministic Validator

Runs before notification leaves the system. Must verify:

- **Recipient** comes from the trusted approver/backup/admin registry — never a model-generated address.
- **Report identity**: the drafted message references the correct `report_id`.
- **Amount**: matches the Firestore report exactly.
- **Legal transition**: e.g. `Pending -> Nudged` valid, `Resolved -> Nudged` invalid.
- **Idempotency**: no existing successful action for the logical key.

Any failure: do not send; create an audit record with `validator_result = blocked`
and a specific `validator_reason`.

---

# Notification Worker

Operates outside the Firestore transaction: read committed action -> validator
-> BLOCK (audit and stop) or PASS -> send -> record success/failure. A mock
Slack/email sender is acceptable for the hackathon. If it supports an
idempotency parameter, use the logical action key. Do not introduce real
Slack/Gmail OAuth unless the repo already has it and it's trivial — OAuth is
explicitly out of scope.

---

# Business-State Transition

A claimed or sent notification is NOT automatically a business-state
transition. Before writing the new state, verify:
`current_state == action.source_state`.

If true: `state_transition = applied`, update the report state.
If false: `state_transition = skipped`, `skip_reason = "report state changed
before transition commit"`. Do NOT overwrite the newer state.

Critical race (must never regress `Resolved`):

```
Pending -> NUDGE claimed -> notification sent -> approver resolves ->
report = Resolved -> worker attempts Pending -> Nudged
```

Expected final result:
```
report.status = Resolved
action.status = sent
action.state_transition = skipped
action.skip_reason = "report resolved before transition commit"
```

---

# Failure Handling

Send fails -> `action.status = failed`, business state unchanged, next tick
retries the same logical action (never a second logical action). Overlapping
ticks on the same report/action/idempotency key -> only one claim succeeds.

---

# Backup Approver

Escalation goes to the primary approver's backup; if none configured, falls
back to a configured admin. Never silently drop an escalation.

---

# Scope Restrictions

Do NOT build: generic approval workflows, multi-approver chains, parallel
approvals, real enterprise OAuth, unnecessary dashboard features, additional
agents, unrelated workflow types, or large-expense prioritization — unless the
core loop is complete and all acceptance tests pass. One workflow done
extremely well is the goal.

---

# Acceptance Tests

## Core
1. Fresh Pending report -> no action, no notification, no state change.
2. Pending older than nudge threshold -> exactly one logical nudge action, correct recipient/amount/report_id, `Pending -> Nudged`.
3. Same report, next tick before escalation threshold -> no duplicate nudge, no state change.
4. Nudged older than escalation threshold since `last_nudged_at` -> backup approver notified, `Nudged -> Escalated`.
5. Resolved report -> no action, no notification, no state modification.

## Adversarial
6. Wrong recipient proposed -> blocked, nothing sent, reason recorded.
7. Wrong amount proposed -> blocked.
8. Wrong report ID proposed -> blocked.
9. Illegal transition proposed (e.g. `Resolved -> Nudged`) -> blocked.
10. Two scheduler ticks concurrently on the same report -> one logical claim, one successful action — assert on `{report_id}:nudge`/`:escalate`, not `tick_id`.
11. No backup approver -> admin fallback notified.
12. Worker crashes after send, before recording result -> document the crash window honestly; do not pretend exactly-once delivery. Test provider-side idempotency if the mock sender supports it.
13. Approver resolves while notification is in flight -> final `report.status = Resolved`; `action.status = sent`, `action.state_transition = skipped`; worker must never regress `Resolved -> Nudged`.

---

# Implementation Process

Work incrementally. Do NOT implement everything blindly in one pass.

**Phase 1 — Repository audit.** Inspect project structure, existing code (Python/FastAPI/Cloud Run), Firestore integration, Gemini/ADK config, existing tests, deployment config, env vars, Docker config. Report what's implemented, missing, and any conflicts. Do not modify code during this phase.

**Phase 2 — Core deterministic engine.** Eligibility, state machine, threshold configuration, logical idempotency. No Gemini required yet.

**Phase 3 — Firestore claim/action records.** Claim transaction, action schema, audit records. Test overlapping claims.

**Phase 4 — Gemini drafting.** Connect Gemini only to the already-decided action. Test with deterministic/injected outputs.

**Phase 5 — Validator.** Implement all adversarial validator tests.

**Phase 6 — Notification worker.** Mock sender, delivery result handling.

**Phase 7 — Conditional state transition.** Implement Scenario 13 before considering the core loop complete.

**Phase 8 — Real deployment.** Cloud Scheduler -> Cloud Run -> Firestore. Run Scenarios 1-5 against the deployed system. Do not declare success based only on local unit tests.

**Phase 9 — Demo preparation.** Only after acceptance tests pass. Demo config: `nudge_threshold = 30s`, `escalation_threshold = 90s`, `scheduler_frequency = 15-30s`. Production documentation: 24h/72h. The scheduler remains the real trigger.

**Phase 10 — Submission packaging.** *(Added: this closes the gap between "the system works" and "the submission is complete" — the hackathon scores these as separate, required deliverables.)*
- Confirm required-tech compliance: Gemini 3.5+ via Gemini API/Vertex AI, at least one Google Agent Framework (ADK), at least one Cloud infra service (Cloud Run/Firestore/Cloud Scheduler all count).
- Write/finalize `README.md` with: text description, features, technologies used, findings/learnings, and step-by-step spin-up instructions a judge could follow without running the project.
- Confirm an architecture diagram exists as a submittable artifact (image or embedded diagram), not only ASCII text in `ARCHITECTURE.md`.
- Confirm the repo is reachable at submission (public, or shared with `testing@devpost.com` and `cloudhackathons@google.com` if private).
- Do not deploy anything that must stay live/costly at judging time — confirm proof-of-deployment (logs, console screenshots, `.run.app` URL) is captured, per the hackathon's own cost-saving guidance.

---

# Working Rules

1. Do not rewrite working code unnecessarily.
2. Do not change the frozen architecture.
3. Prefer small, testable changes.
4. After each meaningful change, run the relevant tests.
5. Never silently weaken an acceptance criterion to make a test pass.
6. If an existing implementation conflicts with the frozen architecture, stop and explain the conflict before making a large redesign.
7. Do not introduce dependencies unless necessary.
8. Keep secrets in environment variables. Never hardcode credentials.
9. Do not claim a test passed unless you actually ran it.
10. Do not claim deployment succeeded unless you actually verified it.
11. Keep the implementation simple enough to explain in a 4-minute hackathon demo.

## First action

Do NOT start coding immediately. First inspect the repository and the existing
implementation. Then give a concise implementation audit with:

```
1. Current architecture found
2. Existing components
3. Missing components
4. Existing tests
5. Deployment status
6. Conflicts with frozen SPEC/ARCHITECTURE
7. Recommended Phase 1 implementation steps
```

After that audit, proceed incrementally with the implementation.
