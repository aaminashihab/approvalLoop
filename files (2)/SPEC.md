# SPEC.md — ApprovalLoop

## 1. Problem / Thesis (this is the first line of the demo video, verbatim)

> "Most agents wait for a prompt. ApprovalLoop acts when nothing happens."

Approvals stall silently because no one is watching the clock. The person who
needs sign-off forgets to follow up, the approver forgets they have something
pending, and the thing just... sits. ApprovalLoop is an agent that treats time
itself as a trigger — it wakes up on a schedule, checks what's stale, and takes
real action without anyone asking it to.

## 2. Target Workflow (locked — do not expand scope after today)

**Expense report approval chasing.**

- A small team submits expense reports.
- Each report needs sign-off from one approver (with a named backup approver).
- Reports are tracked as records in Firestore (`status`, `submitted_at`,
  `approver`, `backup_approver`, `amount`, `last_nudged_at`, `escalated_at`).
- ApprovalLoop runs on a Cloud Scheduler tick (e.g. every hour, sped up for
  demo purposes), checks every open report, and:
  1. If it's been quiet past the nudge threshold → draft and send a Slack/email
     nudge to the approver, referencing the specific report.
  2. If it's been quiet past the escalation threshold → notify the backup
     approver instead, and flag the record as escalated.
  3. If it's already resolved → do nothing (idempotent).

**Why this workflow specifically:** it has an unambiguous staleness signal
(elapsed time), a clean two-tier escalation path, real financial stakes (so
"a stalled approval is bad" is self-evidently true to a judge), and no
sensitive real data is needed — mock records are entirely convincing.

## 3. State Machine (informal — formalized in ARCHITECTURE.md on Day 2)

```
Pending --(nudge threshold passed)--> Nudged
Nudged --(escalation threshold passed)--> Escalated
Pending/Nudged/Escalated --(approver acts)--> Resolved
```

## 4. User Stories

1. As a submitter, I want my report chased automatically so I don't have to
   personally nag my approver.
2. As an approver, I want a nudge that tells me exactly what's waiting and
   why it matters (amount, age, submitter) — not a generic "you have a task."
3. As an org, I want a backup approver notified if the primary goes dark,
   without duplicate or conflicting approvals happening.
4. As an auditor, I want every action ApprovalLoop takes logged with a
   timestamp and reason, so I can reconstruct what happened and why.

## 5. Edge Cases (design for these now, don't discover them on Day 9)

| Edge case | Required behavior |
|---|---|
| Approver already resolved it, but a scheduler tick fires before sync | The claim transaction re-reads current report state and refuses to claim an action that is no longer eligible — no nudge is sent. (If resolution happens *after* claiming but before the final state write, the conditional transition guard in ARCHITECTURE.md Section 5 handles it — see Scenario 13.) |
| Nudge already sent, tick fires again before threshold for escalation | No duplicate nudge (idempotency via `last_nudged_at`) |
| No backup approver configured | Escalate to a configured admin fallback, never silently drop it |
| Report amount is unusually large | (Stretch) flag for priority nudging — optional, don't build unless core loop is solid by Day 9 |
| Agent's draft message references wrong report or wrong person | Deterministic validator blocks the send — this must never reach the notification tool on a hallucinated recipient/amount |

## 6. Success Criteria (this doubles as the Day 11–13 eval rubric — write it precisely)

An end-to-end run is successful if, given a seeded set of mock reports:

- [ ] Reports past the nudge threshold receive exactly one nudge, addressed
      correctly, referencing the correct amount/age.
- [ ] Reports past the escalation threshold notify the backup approver, and
      the original approver is not double-messaged in the same tick.
- [ ] Resolved reports are never touched.
- [ ] Every state transition is written to Firestore with a timestamp and
      the reason the agent acted (for audit).
- [ ] No action is taken that didn't pass the deterministic validator
      (this is checked in tests, not just evals).

## 7. Explicitly Out of Scope (for this hackathon build)

- Real Slack/Gmail OAuth with a live company workspace (mock the send, or
  use a sandbox workspace — don't burn Day 3 on API approval workflows).
- Multi-approver / parallel sign-off chains.
- A general-purpose "approval platform" for arbitrary workflow types —
  one workflow, done well, beats a broad half-built platform.

## 8. Threshold decision (resolved)

Thresholds are config-driven, not hardcoded, and take different values per
environment:

- **Automated tests:** 2s / 5s (fast, no real waiting).
- **Demo recording:** 30s / 90s, explicitly labeled on-screen as compressed
  demo thresholds — chosen to fit the full scenario set inside a ~4 min video
  without a long unedited take.
- **Production (documented, not deployed):** 24h / 72h.

The Cloud Scheduler tick remains the real, unmodified trigger in every
environment — only the eligibility threshold it's checked against changes.
Nothing about the trigger mechanism itself is faked.

**Scheduler frequency is a separate config value from these thresholds.** The
scheduler asks "should I check now?"; eligibility code asks "is this report
actually due?" If the scheduler fires less often than the threshold, behavior
becomes unpredictable — e.g. a 60s tick against a 30s threshold means the actual
nudge could land anywhere in a 60s window instead of close to 30s. For the demo
recording, configure Cloud Scheduler to fire every 15-30s, so polling is visibly
frequent relative to the 30s/90s demo thresholds.
