# ARCHITECTURE.md — ApprovalLoop
**Status: FROZEN v4.** Design is closed. This revision adds two implementation
invariants surfaced during review — these are correctness requirements on the
*code*, not further changes to the design. No further architecture revisions
anticipated before implementation begins.

---

## 1. Design principle: LLM proposes, code disposes

The Gemini-backed agent decides *what the message should say*. It never decides
*whether an action is allowed to happen or whether business state changes*. That
is enforced entirely by deterministic code — the state machine, the validator,
the idempotency key, and the conditional state transition (Section 5) —
independent of anything the model outputs.

```
                 CLOUD SCHEDULER
                       |
                       v
                 CHECK REPORTS
                       |
                       v
             +-------------------+
             | Firestore state   |
             | + current time    |
             +---------+---------+
                       |
                       v
              DETERMINISTIC ELIGIBILITY
                       |
             "NUDGE EXP-104"
                       |
                       v
                 GEMINI AGENT
                 drafts wording
                       |
                       v
          FIRESTORE CLAIM TRANSACTION
     (commits intended_action; establishes
      logical ownership of this action)
                       |
                       v
                 NOTIFICATION
                    WORKER
                       |
                       v
              DETERMINISTIC VALIDATOR
        (safety check: is this communication
              actually safe to send?)
                       |
                 +-----+-----+
                 |           |
               BLOCK        PASS
                 |           |
                 v           v
              AUDIT        SEND
                             |
                       +-----+-----+
                       |           |
                     FAIL         SENT
                       |           |
                       v           v
                    RETRY   CONDITIONAL STATE
                            TRANSITION (only if
                            current_state ==
                            action.source_state)
                                    |
                                    v
                                AUDIT LOG
```

**The claim transaction and the validator answer different questions:**
- The **claim transaction** establishes that this logical action belongs to this
  report — ownership, not safety.
- The **validator** establishes that the proposed communication is safe to send —
  correct recipient, correct details, legal transition.

Both must pass before anything reaches an external system.

**Rule: Gemini never outputs the authoritative state.** Firestore + the
eligibility calculation are the only source of truth for what state a report is
in. Gemini receives an instruction already decided by code — e.g. `"Action
required: NUDGE report EXP-104"` — and its job is only to produce the wording.

## 2. No external I/O inside a Firestore transaction

**Problem:** Firestore automatically retries transactions on contention. If a
transaction body includes an external side effect (a Slack/email send), a retry
can cause that side effect to fire more than once.

**Fix — transactional outbox pattern:**

1. **Firestore claim transaction** (fast, no network calls): re-read the report's
   current state, verify eligibility, write an `intended_action` record, commit.
2. **Notification worker** (outside any transaction): reads the committed intent,
   validates (Section 3), sends, and separately records the result.

### Idempotency key — logical action identity, not per-tick

```
nudge key:      {report_id}:nudge
escalation key: {report_id}:escalate
```

At most one committed claim per key, ever. `tick_id` is a separate observability
field on the action record — useful for debugging which scheduler run triggered
what — but is not part of the dedup key.

A failed send does **not** create a new logical action (no `EXP-104:nudge #2`).
It retries the same logical action: `EXP-104:nudge, status: failed -> retry -> sent`.
This preserves a single, coherent audit trail per action rather than fragmenting
it across retry attempts.

### What this does and doesn't guarantee

> ApprovalLoop guarantees exactly-once *action claiming* per report per action
> type, and prevents duplicate sends under normal worker retries and overlapping
> scheduler ticks. It does not claim exactly-once delivery under a crash between
> send and record (see Scenario 12 in TEST_SCENARIOS.md) — that would require a
> provider-side idempotent send API, out of scope here.

Scenario 2's "exactly one nudge sent" should be read as: exactly one successful
nudge under normal execution/retry conditions; the crash-between-send-and-record
limitation is separately covered and acknowledged, not silently excluded.

## 3. The deterministic validator

Runs after the claim transaction commits and the worker picks up the intent,
before anything leaves the system. Plain code, no model call. Checks:

- `recipient` is present in the approver/backup-approver registry.
- `amount` and `report_id` in the drafted message match the Firestore record
  exactly (catches hallucinated details).
- The proposed action is a legal transition given current state.
- No existing successful claim under this action's idempotency key.

Any failure blocks the send and logs `validator_result: blocked` with
`validator_reason`.

### Action record schema

```
action_id
report_id
action_type          (nudge | escalate)
source_state
target_state
tick_id
idempotency_key
recipient
amount
created_at
validator_result      (pass | blocked)
validator_reason
message
sent_at
status                (claimed | sent | failed | blocked)
state_transition       (applied | skipped)
skip_reason
error
```

## 4. Formal state machine

Escalation timing is measured from the nudge, not from submission:

```
Pending
  |  submitted_at + nudge_threshold elapsed
  v
Nudged
  |  last_nudged_at + escalation_threshold elapsed
  v
Escalated

Pending / Nudged / Escalated  --[approver acts]-->  Resolved
Resolved  --[any]-->  Resolved   (terminal, no-op)
```

Guards are evaluated in code, never inferred by the LLM.

## 5. Claiming an action vs. changing business state — with the conditional guard

An action record moving to `status: sent` is not the same event as the report's
business state changing. The business state transitions **only after** the
notification workflow succeeds, **and only if the report is still in the
action's `source_state`** at the moment of the final write.

### Implementation invariant (mandatory, not optional)

**The final business-state transition must be conditional on the report still
matching `action.source_state`.** Without this guard, the following race
overwrites a legitimate resolution:

```
t0  Report = Pending
t1  Scheduler claims NUDGE          (source_state recorded as Pending)
t2  Gemini drafts message
t3  Notification sends successfully
t4  Approver resolves the report    (Report = Resolved)
t5  Worker attempts Pending -> Nudged
```

If the worker blindly writes `Nudged` at t5, it overwrites `Resolved` — directly
violating "Resolved reports are never touched," the strongest requirement in this
system.

**Required logic at transition time:**

```
if current_state == action.source_state:
    transition -> action.target_state
    state_transition: applied
else:
    do not modify business state
    state_transition: skipped
    skip_reason: f"report state changed before transition commit (expected={action.source_state}, found={current_state})"
```

`skip_reason` is generated from one template, everywhere — never hand-written
per scenario. This is deliberate: a single code path producing the reason
string means the audit trail and any test asserting on it can never drift apart
from each other. For the specific race in this section, that resolves to:

```
skip_reason == "report state changed before transition commit (expected=Pending, found=Resolved)"
```

If the approver wins the race, the report correctly ends at `Resolved`, and the
notification action record remains truthful: `status: sent, state_transition:
skipped, skip_reason: <template above>`. The notification having been sent is
not erased — it's accurately recorded as having arrived too late to matter,
which is honest and auditable rather than silently wrong.

## 6. Component map

| Component | Role | Tech |
|---|---|---|
| Trigger | Fires the check on a schedule | Cloud Scheduler |
| Decoupling (optional) | Buffers scheduler tick from agent invocation | Pub/Sub |
| Agent runtime | Runs the ADK agent loop, calls Gemini for drafting | Cloud Run |
| State store | Reports, state machine, idempotency keys, audit log | Firestore |
| Validator | Deterministic pre-send checks | Plain code, no model call |
| Notification worker | Sends message, records delivery result | Cloud Run (same service) or mocked sender for demo |

## 7. Failure handling

- **Send fails:** action record gets `status: failed`; business state untouched;
  next tick retries the same logical action.
- **Overlapping ticks:** only one claim per logical key ever succeeds.
- **Invalid transition proposed:** validator blocks; loop continues.
- **Approver resolves mid-flight (Section 5 race):** conditional transition guard
  prevents overwrite; recorded as `state_transition: skipped`.
- **Worker crashes between send and record:** acknowledged, scoped gap (Scenario 12).

## 8. What this buys for the judging rubric

- **Innovation & Operational Utility:** time-triggered, not prompt-triggered.
- **Architectural Discipline:** explicit deterministic/non-deterministic boundary,
  correct logical idempotency key, claim/validate distinction, race-safe
  conditional state transition, honestly-scoped delivery claim, full audit trail.
- **Demo & Production Readiness:** every claim, send attempt, and transition
  (applied or skipped) is timestamped in Firestore for a live, unedited demo.

---

## Revision log

- v1: initial design, external send inside Firestore transaction (unsafe).
- v2: transactional outbox pattern introduced; idempotency claim initially
  overstated as exactly-once delivery.
- v3: idempotency key corrected to logical action identity; escalation timing
  corrected to measure from `last_nudged_at`; action claim and business state
  transition explicitly decoupled; delivery claim scoped honestly.
- v4 (frozen): added mandatory conditional-state-transition guard against the
  approver-resolves-during-notification race; corrected Section 1 diagram to
  match Section 2's claim-then-validate ordering (previously inconsistent);
  clarified claim vs. validate as answering ownership vs. safety.
