# ApprovalLoop — 17-Day Agentic Engineering SDLC Plan
**All Things Agentic Hackathon — Taskmaster Track**
Deadline: Sept 1, 2026, 5:30am GMT+5:30 (17 days from Aug 15, 2026)

---

## 1. The Use Case

**Problem:** Approvals stall silently. Expense reports, PR/contract sign-offs, vendor
onboarding, access requests — they sit in someone's inbox because nobody is watching
the clock. Existing "agents" are chatbots: they wait for a human to open them and ask.

**ApprovalLoop** is an agent that treats *time itself* as an event. It runs on a
schedule (not a prompt), checks the state of every open approval, and takes real
action — drafts and sends a context-aware nudge, escalates to a backup approver after
N days of silence, and writes every decision to an auditable ledger. No one has to
remember to chase anything.

**Why this fits Taskmaster:** it's a genuine multi-step chore (tracking, judging
staleness, drafting the right message, sending it to the right channel, escalating
correctly) and it *takes action*, not just conversation.

**Why this is judged well specifically (mapped to the rubric):**

| Criterion | Weight | How ApprovalLoop scores it |
|---|---|---|
| Innovation & Operational Utility | 40% | Time-triggered autonomy (Cloud Scheduler tick = first-class event) is the "reaction to silence" pattern — most submissions will be reactive chat loops. |
| Architectural Discipline & Tech Stack | 30% | Deterministic validator + state machine + audit ledger directly demonstrates "agentic engineering" (tests/evals/guardrails) over vibe coding. |
| Demo & Production Readiness | 30% | Cloud Run + Cloud Scheduler + Firestore logs give unambiguous, screenshot-able proof it's running on Google Cloud autonomously — no manual trigger needed on camera. |

**Prize hedge:** Position the README and video to also make a clean case for
**Best Architectural Design** ($5k) via the state-transition diagram and validator —
if Taskmaster ($20k) goes to a flashier UI, this is the fallback.

---

## 2. Required Stack (per hackathon rules)

- Gemini 3.5+ (via Gemini API or Vertex AI)
- One Google Agent Framework — **Google ADK** (best fit for the agent loop + tool orchestration)
- One Google Cloud infra service — **Cloud Run** (agent service) + **Cloud Scheduler** (the trigger) + **Firestore** (state/ledger)
- Optional stretch: Pub/Sub for decoupling the scheduler tick from the agent invocation (helps the "decouple systems" line in the architecture criterion)

---

## 3. The SDLC, Applied

The whitepaper's core claim is that AI compresses **implementation** but not
**requirements, architecture, or verification** — so that's where your time should
concentrate. Below, each phase names what's built and which whitepaper concept it
operationalizes.

### Phase 1 — Requirements & Planning (Day 1–2)
*Whitepaper concept: requirements become a live conversation, not a handoff.*

- Write a one-paragraph problem/thesis statement — this becomes the first 20 seconds
  of your demo video, verbatim: *"Most agents wait for a prompt. ApprovalLoop acts
  when nothing happens."*
- Pick ONE concrete approval workflow to demo end-to-end (don't build a generic
  platform — pick e.g. "expense report approvals over Slack/email"). Judges reward
  a tight, complete loop over broad, half-broken scope.
- Draft user stories / edge cases with the AI: what counts as "stale"? What happens
  on escalation failure? What if the approver replies mid-check?
- **Deliverable:** `SPEC.md` — problem statement, one target workflow, success
  criteria in plain language (this doubles as your eval rubric later).

### Phase 2 — Design & Architecture (Day 2–5)
*Whitepaper concept: architecture is the one phase AI can't do for you — trade-offs
require human judgment.*

- Design the state machine: `Pending → Nudged → Escalated → Resolved` (or similar).
  This is your single most important artifact for the "Architectural Discipline" score.
- Decide static vs. dynamic context for the agent (see Section 4).
- Decide the deterministic boundary: what does the LLM *decide* (who/what/when to
  message) vs. what does *code* enforce (state transitions, no double-sends, no
  hallucinated recipients)? This "LLM proposes, code disposes" split is your core
  architectural story — write it into the README explicitly.
- **Deliverable:** `ARCHITECTURE.md` + diagram (Gemini ↔ ADK agent ↔ Firestore ↔
  Cloud Scheduler ↔ notification channel). This is the required submission artifact —
  build it now, not on day 16.

### Phase 3 — Implementation (Day 5–11)
*Whitepaper concept: this is where AI compresses time the most — but verify, don't
just accept.*

- Scaffold with ADK. Use a coding agent (Claude Code / Gemini CLI) in **conductor
  mode** for the core state machine (you want to read every line here — it's your
  correctness-critical path) and **orchestrator mode** for boilerplate (notification
  templates, Firestore schema, deploy scripts).
- Build the harness pieces explicitly, not implicitly:
  - `AGENTS.md` — agent's role, hard rules ("never send to an address not in the
    approver registry", "never skip the deterministic validator")
  - Tools: calendar/email/Slack send, Firestore read/write, escalation lookup
  - Guardrails/hooks: reject any agent action that didn't pass the validator
  - Orchestration: Cloud Scheduler → Pub/Sub → Cloud Run → ADK agent loop
- Deploy early (Day ~7) to a real Cloud Run service, even if half-working — you need
  real logs/traces for the demo, and late deploys are the #1 hackathon failure mode.
- **Deliverable:** working end-to-end loop, deployed, with at least one real
  scheduled run visible in Cloud Console.

### Phase 4 — Testing & QA (Day 11–13)
*Whitepaper concept: tests verify the deterministic parts; evals verify the
non-deterministic parts. This is the single biggest "agentic engineering" signal you
can show judges — most teams will skip it entirely.*

- **Tests** (code-checked): state machine transitions, Firestore writes, no-duplicate-send
  logic, validator rejection paths.
- **Evals** (rubric/LM-judge-checked): does the agent draft an appropriately-toned
  nudge? Does it correctly judge staleness? Build a tiny labeled eval set (5–10
  scenarios) and run it — screenshot the pass rate for your README.
- This is exactly the "output eval + trajectory eval" distinction from the
  whitepaper — capture both: did it produce the right message (output), and did it
  take the right sequence of tool calls to get there (trajectory).
- **Deliverable:** `evals/` folder with scenarios + results. This is cheap to build
  and disproportionately strengthens the Architectural Discipline score.

### Phase 5 — Code Review & Deployment Hardening (Day 13–15)
*Whitepaper concept: AI as first-pass reviewer; human judgment on the rest.*

- Run an AI-assisted review pass focused on: hallucinated imports, missing error
  handling, credential leaks, and any place the agent could act without going
  through the validator.
- Confirm production-readiness signals judges explicitly want: Cloud Run dashboard
  screenshot, Vertex AI/Gemini API logs, a real `.run.app` URL, visible timestamps
  proving autonomous (unprompted) execution.
- Write the `README.md` spin-up instructions — judges may not run it, but
  reproducibility is scored, so make it real and testable.
- **Deliverable:** clean repo, hardened deploy, reproducible README.

### Phase 6 — Demo & Submission (Day 15–17)
*Whitepaper concept: verification, judgment, and direction are the new craft —
prove yours in 4 minutes.*

- Script the video tightly (~4 min): problem (20s) → live autonomous trigger firing
  on Cloud Scheduler with visible timestamp → agent taking real action → Firestore
  ledger/audit trail → architecture diagram walkthrough → close on the
  "LLM proposes, code disposes" architectural story.
- Do **not** use a mock timer or a manual "Run" button in the video — this was
  flagged as the single biggest way to lose credibility on autonomy.
- Submit: hosted URL (if feasible), repo, architecture diagram, ~4 min video,
  write-up (features, tech, findings/learnings).
- Optional bonus points: publish a short build-log post with the
  `#AllThingsAgenticHackathon` hashtag — cheap, explicitly rewarded.

---

## 4. Context Engineering Plan (for the agent itself)

| Context type | Static (always loaded) | Dynamic (loaded on demand) |
|---|---|---|
| Instructions | Core role + hard rules in `AGENTS.md` | — |
| Knowledge | Approver registry, escalation policy | Per-workflow docs fetched at runtime |
| Memory | — | Firestore state per approval thread |
| Examples | 2–3 few-shot nudge/escalation templates | — |
| Tools | Firestore, notification-send, validator | Calendar/CRM lookups, only if triggered |
| Guardrails | Validator, rate limits, allow-list of recipients | — |

Keep the static context lean — the whitepaper's point that "too much static context
dilutes signal" applies directly here; don't stuff the whole approver database into
every prompt.

---

## 5. Risk Register

| Risk | Mitigation |
|---|---|
| Demo relies on a mock timer, loses autonomy credibility | Deploy real Cloud Scheduler early; demo a live tick |
| No test/eval coverage → looks like vibe coding | Budget Day 11–13 non-negotiably for this |
| Scope creep into a "platform" | Lock to one workflow after Day 2 |
| Late deploy → no real Cloud logs | Deploy a rough version by Day 7 |
| Video runs long / buries the thesis | Script and time it before Day 16 |

---

## 6. Daily Checkpoint Summary

| Days | Focus |
|---|---|
| 1–2 | Spec + one target workflow locked |
| 2–5 | Architecture: state machine, validator boundary, diagram |
| 5–11 | Build + early real deploy |
| 11–13 | Tests + evals |
| 13–15 | Review, hardening, README |
| 15–17 | Demo video + submission |
