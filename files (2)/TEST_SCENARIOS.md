# TEST_SCENARIOS.md — ApprovalLoop acceptance criteria

These are not aspirational. This is the definition of done for the core loop.
Nothing else gets built until all of these pass against the real deployed system
(Cloud Scheduler tick -> Cloud Run -> Firestore), not just unit-tested in isolation.

Each scenario should be checkable two ways:
- **Test** (code-checked, deterministic): does the state/record end up correct?
- **Eval** (rubric-checked): for scenarios involving Gemini's drafted wording, is
  the message appropriately worded and does it reference correct details?

## Core scenarios

| # | Scenario | Setup | Expected result | Type |
|---|---|---|---|---|
| 1 | Fresh pending report | Report submitted seconds ago | No action taken | Test |
| 2 | Pending past nudge threshold | `submitted_at` > `nudge_threshold` ago | Exactly one nudge sent, correct recipient/amount/report_id, `Pending -> Nudged` | Test + Eval |
| 3 | Same report, next tick | Report already `Nudged`, tick fires again before `escalation_threshold` elapses | No duplicate nudge; no state change | Test |
| 4 | Nudged past escalation threshold | `last_nudged_at` > `escalation_threshold` ago | Backup approver notified, `Nudged -> Escalated` | Test + Eval |
| 5 | Resolved report | Report status is `Resolved` | Absolutely nothing happens on any subsequent tick | Test |

## Adversarial / edge cases

| # | Scenario | Expected result |
|---|---|---|
| 6 | LLM proposes wrong recipient | Validator blocks; `validator_result: blocked`, `validator_reason` logged; nothing sent |
| 7 | LLM proposes wrong amount | Validator blocks |
| 8 | LLM proposes wrong report_id | Validator blocks |
| 9 | LLM (or a bug) proposes an illegal transition, e.g. `Resolved -> Nudged` | Validator blocks — state machine legality is checked in code, not trusted from the model |
| 10 | Overlapping scheduler ticks fire concurrently on the same report | Exactly one action results — verified by asserting only one committed claim exists under the logical key `{report_id}:nudge` (or `:escalate`), not merely that `tick_id`s differ |
| 11 | No backup approver configured for a report needing escalation | Falls back to a configured admin recipient — never silently drops the escalation |
| 12 | Worker crashes after send, before recording result (simulate by killing the process mid-send in a test harness) | Documented gap — see ARCHITECTURE.md Section 2. If the mock sender supports idempotency natively, verify it suppresses the duplicate; if not, this is an explicitly acknowledged limitation, not a hidden bug |
| 13 | Approver resolves the report while a nudge notification is in flight (simulate: claim + send succeed, then flip report to `Resolved` before the final state-write executes) | Notification may complete, but the worker must NOT overwrite `Resolved` with `Nudged` — see the exact assertion below the table |

**Scenario 13 — required assertion (all four must hold, not just the first):**
```
report.status              == "Resolved"
action.status               == "sent"
action.state_transition     == "skipped"
action.skip_reason          == "report state changed before transition commit (expected=Pending, found=Resolved)"
```
Asserting `action.status == "sent"` alone is not sufficient — that only proves
the notification went out, not that the race guard fired. All four fields
together are what proves ARCHITECTURE.md Section 5's invariant actually held.
The `skip_reason` value comes from the single template defined in
ARCHITECTURE.md Section 5 — it is generated, not hand-written per scenario, so
implementation and test can never drift apart on wording.

## Threshold configuration (not hardcoded)

`nudge_threshold` and `escalation_threshold` are read from config, not hardcoded
in application logic — they take different values per environment:

| Environment | nudge_threshold | escalation_threshold |
|---|---|---|
| Automated tests | 2s | 5s (fast, no real waiting) |
| Demo recording | 30s | 90s (compressed, labeled on-screen) |
| Production (documented, not deployed) | 24h | 72h |

## How this maps to the demo

Scenarios 1-5, run live against the deployed system with short synthetic
thresholds (2 min / 5 min), *are* the demo. See DEMO_SCRIPT.md — the video
should show these five states occurring in real time against the actual
Firestore ledger, not a slide describing them.

## Definition of done for Day 3-9 (implementation)

- [ ] Scenarios 1-5 pass against the deployed Cloud Run service, verified by
      reading the actual Firestore state after each tick — not mocked locally.
- [ ] Scenarios 6-11 pass, ideally via an injected/mocked "bad LLM output" test
      harness (feed the validator a deliberately wrong proposal and confirm it
      blocks) — you should not need a misbehaving Gemini to test this path.
- [ ] Scenario 12's limitation is written into the README's claims section
      exactly as scoped in ARCHITECTURE.md Section 2 — not overstated, not hidden.
- [ ] Every action, blocked or sent, produces an `action_id` record matching the
      schema in ARCHITECTURE.md Section 3.
- [ ] A successful notification must never regress a report from `Resolved` back
      to `Nudged`/`Escalated`; the final state transition is conditional on the
      report still matching the action's `source_state` (ARCHITECTURE.md
      Section 5). Verified by Scenario 13.
