# DEMO_SCRIPT.md — ApprovalLoop (~4 minutes)

Rule: everything shown must be a real, live event against the deployed system —
no mock timers, no manual "run" button, no staged slides standing in for actual
Firestore state. This is what separates "looks autonomous" from "is autonomous"
on camera.

**Threshold policy for this recording:** the deployed instance used for filming
is configured with `nudge_threshold = 30s`, `escalation_threshold = 90s` — real
values, checked by real code, against a real Cloud Scheduler trigger. State this
explicitly on screen once (e.g. as a caption during 3:15-3:40): "Compressed demo
thresholds: 30s/90s. Production default: 24h/72h." The scheduler itself is never
altered or faked — only the eligibility window it checks against is smaller for
the recording.

**On cuts:** waiting out 30s and 90s of real time in a single unedited take is
allowed and simplest. If a hard cut is used to skip dead air, it must jump
between two visible, real timestamps in the Cloud Run logs or Firestore console
(e.g. cut from `10:00:03` to `10:00:31`) so the elapsed time is verifiable from
what's on screen — never a cut to a graphic or a countdown that implies time
passed without evidence.

## 0:00–0:20 — Thesis

On screen: nothing but the line, spoken and shown as text.

> "Most agents wait for a prompt. ApprovalLoop acts when nothing happens."

Cut immediately to the problem: approvals stall because no one is watching the
clock. One sentence, no more.

## 0:20–0:45 — Submission (the baseline)

- Show a mock expense report being submitted (script or seeded Firestore write).
- Show the Firestore record: `status: Pending`, `submitted_at: <now>`.
- No agent action yet — this establishes the "quiet" state the whole demo hinges on.

## 0:45–1:30 — First scheduler tick (nudge, ~30s after submission)

- Show the **real** Cloud Scheduler console / Cloud Run logs with a visible
  timestamp — this is the "unprompted" proof.
- Narrate live: "30 seconds have passed — compressed for this demo. Nobody
  asked ApprovalLoop to check. It checks anyway."
- Show, in sequence, on screen:
  - eligibility calculation determines nudge is due (code, not the model)
  - Gemini drafts the message (show the drafted text)
  - validator passes (show the validator's pass log line)
  - notification sent (mock Slack/email showing the message)
  - Firestore updates: `Pending -> Nudged`, action record with full audit fields

## 1:30–1:50 — Idempotency proof (scenario 3)

- Deliberately trigger a second tick before the escalation threshold.
- Show: no duplicate nudge, no state change, log line showing the idempotency
  check short-circuited the action.
- Narrate: "Same report, next tick — nothing happens. It already acted once."

## 1:50–2:40 — Escalation (scenario 4)

- Reach the escalation threshold: 90s since the nudge, in the demo's
  compressed timeline (production default: 72h). This is the on-screen caption
  moment referenced above.
- Show backup approver receiving the escalation notification.
- Show Firestore: `Nudged -> Escalated`.

## 2:40–3:00 — Resolved report is inert (scenario 5)

- Show a second, already-resolved report sitting untouched across multiple
  ticks — the negative case matters as much as the positive ones.

## 3:00–3:30 — The validator blocking a bad proposal (scenario 6-9)

- This is the architectural differentiator — don't cut it for time.
- Inject a deliberately wrong proposal (wrong recipient or illegal transition)
  into the validator via the test harness.
- Show it get blocked, with `validator_result: blocked` and the reason logged.
- Narrate: "The model drafts the message. It never decides whether it's allowed
  to send. That's enforced in code, independently, every time."

## 3:30–3:50 — Architecture diagram walkthrough

- 15-20 seconds on the diagram: Scheduler -> Agent -> Firestore claim -> validator
  -> notification worker -> result recorded.
- One sentence on the fix that made it correct: "The send never happens inside the
  database transaction — that's what makes retries safe."

## 3:50–4:00 — Close

- Cloud Run dashboard or Vertex AI logs, visible, confirming it's running on
  Google Cloud.
- Final line: "Generation is easy. Verification is the hard part. That's what
  ApprovalLoop is built around."

## Things this script deliberately does NOT do

- No manual trigger button pressed on camera.
- No claim of "guaranteed exactly-once delivery" — if narrating the reliability
  story, use the scoped claim from ARCHITECTURE.md Section 2, not a stronger one.
- No UI tour longer than necessary to see the state changes — the ledger and logs
  are the interesting part, not a dashboard.
