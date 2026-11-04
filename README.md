# ApprovalLoop

**A governance gateway between LLM agents and actions that move money.** Agents may only *propose* an action, such as a refund, an account credit or a discount. Deterministic code checks the agent's identity, screens the text, and applies a versioned policy that either runs the action, holds it for a person, or blocks it. A small web console lets an approver decide held actions.

> AI proposes. Deterministic policy decides. Infrastructure executes.

**Status:** a working prototype and portfolio project, not a production system. The governance core is real and well tested (210 automated tests, including tests against a real PostgreSQL server). Some advertised integrations are only adapters or demos; see [What is real and what is not](#what-is-real-and-what-is-not).

---

## Contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [What is real and what is not](#what-is-real-and-what-is-not)
- [Policy limits](#policy-limits)
- [Project layout](#project-layout)
- [Run it locally](#run-it-locally)
- [Configuration](#configuration)
- [API overview](#api-overview)
- [Tests and evaluation](#tests-and-evaluation)
- [Deploy to Google Cloud](#deploy-to-google-cloud)
- [Known limitations](#known-limitations)
- [Further reading](#further-reading)
- [License](#license)

---

## What it does

1. **Gates agent actions.** Every proposal from an agent goes through one gateway. It is allowed and executed automatically, held for a human approver, or denied, depending on fixed rules, not on what the model writes.
2. **Lets a person decide held actions.** Held actions wait in a durable queue. An operator approves or rejects them in the console, and every decision is recorded with the policy version, the reason and who decided.
3. **Chases stalled expense approvals.** A scheduled "tick" finds expense reports waiting too long, reminds the approver, then escalates to a backup. An LLM may write the reminder wording; code supplies every fact in the message.

## How it works

```
Agent (finance / support / sales)
   │  AgentActionProposal + signed credential
   ▼
Agent Gateway ──► 1. Identity: HMAC or Google OIDC token, agent registered, active, action allow-listed, request not replayed
              ──► 2. Text screening: Google Cloud Model Armor (when credentials exist) + pattern filter
              ──► 3. Policy: versioned limits per agent profile, plus a daily cap per agent
   │
   ├── ALLOW ──► idempotent executor ──► audit trail
   ├── HOLD  ──► paused workflow ──► human approves / rejects in the console ──► executor or audit trail
   └── DENY  ──► audit trail (nothing runs)
```

The expense-reminder loop (`POST /api/tick`) is separate:

```
open reports → overdue? → claim (no duplicates) → LLM drafts wording → code builds the message
→ validator checks recipient, amount, report and state → policy → send → state change only if nothing changed meanwhile
```

Key design choices:

- **The model never holds authority.** Whether an action runs depends only on structured fields (agent, action, amount, currency, recipient), never on the justification text.
- **Fail closed.** Unknown policy profiles, unsupported currencies, invalid amounts, missing credentials and unconfigured OIDC audiences all lead to denial or human review, never execution.
- **At most once.** Approvals are single-winner (a conditional database update), and execution uses idempotency keys.

## What is real and what is not

| Area | Status | Details |
|---|---|---|
| Gateway, identity, policy, daily cap | **Implemented and tested** | Policy decisions matched the documented limits in 20,040 of 20,040 evaluated cases. |
| Human approval queue | **Implemented and tested** | Durable in PostgreSQL; approvals expire after 24 h; an agent that has been disabled cannot have its actions approved. |
| Approval atomicity | **Implemented and tested** | Single winner across separate database connections. Not yet load-tested on Cloud SQL. |
| Request-bound agent tokens | **Implemented** | Tokens are tied to one request and a hash of the proposal. Enforced by default only in production. |
| Replay protection | **Implemented** | Stored in the database, so it holds across instances. |
| PostgreSQL storage | **Implemented and tested** | Schema created on start-up. Without `DATABASE_URL` the API uses in-memory storage (refused in production). |
| Operator console (React) | **Implemented** | Approvals, activity, agents, expenses and a sandbox. |
| LLM use (Gemini) | **Limited** | The model writes justifications and reminder wording only. Amounts, recipients and actions come from code, not the model. With no `GEMINI_API_KEY`, fixed templates are used. |
| Google Cloud Model Armor | **Optional** | Used only when Google credentials are available. Otherwise it is silently skipped and only the pattern filter runs. |
| Pattern filter | **Partial** | Catches known injection phrases, including disguised ones (look-alike letters, hidden characters, digit swaps, spacing, Base64). It does **not** catch reworded instructions: 0 of 8 in our tests. The policy limits, not this filter, bound what an attack can achieve. |
| "Multi-agent" fleet | **Demo only** | Three agents (finance, support, sales) send proposals independently. A `FleetOrchestrator` chains four helper agents, but it is used only in tests and its agent is not registered in the running app. |
| Slack and SMTP notifications | **Adapters only** | `SlackNotificationProvider` and `EmailNotificationProvider` exist, but the running app always uses the mock notifier. |
| Executing real refunds, credits or discounts | **Not implemented** | Execution is simulated by the mock notifier. |
| Async task runtime with leases | **Implemented, not wired** | Implemented and tested, but not used by any API route. |

## Policy limits

Defined in `backend/approval_loop/policy/policy_engine.py`. The server enforces these; the console shows a read-only copy.

| Profile | Runs automatically | Needs a person | Blocked | Daily automatic cap per agent |
|---|---|---|---|---|
| `finance-v3` (INR) | under 5,000 | 5,000 – 25,000 | above 25,000 | 50,000 |
| `finance-v3` (USD) | under 50 | 50 – 250 | above 250 | 500 |
| `support-v1` (INR) | under 2,000 | 2,000 – 10,000 | above 10,000 | 20,000 |
| `support-v1` (USD) | under 20 | 20 – 100 | above 100 | 200 |
| `sales-v1` (discount %) | up to 10% | over 10% – 30% | above 30% | none |

Once an agent's automatically executed total for the day would exceed its cap, further proposals are held for a person.

## Project layout

```
backend/approval_loop/
  api/            FastAPI app, routes, operator and scheduler auth
  gateway/        AgentGateway: identity → screening → policy → decision
  identity/       agent tokens (HMAC, Google OIDC), replay protection
  guardrails/     Model Armor client + pattern filter
  policy/         versioned policy profiles and daily caps
  memory/         Memory Bank: workflows, decisions, human approval state
  engine.py       expense-reminder loop
  agent/          fleet agents, prompts, wording drafter
  storage/        repository interface, in-memory and PostgreSQL implementations, SQL schema
  worker/         notification providers (mock, Slack, SMTP)
  runtime/        async task runtime (not wired to routes)
backend/tests/    210 tests
frontend/         React + TypeScript + Tailwind operator console
evals/            demo and simulation scripts
paper/            IEEE-style evaluation paper and reproducible harness
docs/             study guide and architecture diagram
skills/           procedural "skill" files loaded by the reminder loop
```

## Run it locally

**Requirements:** Python 3.10+, Node.js 20+. PostgreSQL is optional locally.

**1. Backend**

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash); on macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
APP_ENV=demo python -m uvicorn approval_loop.api.app:app --port 8080
```

This runs with in-memory storage, which is lost on restart. To use PostgreSQL, set `DATABASE_URL` first:

```bash
export DATABASE_URL=postgresql://approvalloop:approvalloop@localhost:5432/approvalloop
```

**2. Console**

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000; the dev server forwards `/api` to port 8080. The console asks for an operator key: in local demo mode, this is the value of `SCHEDULER_API_KEY` (a development default is set in `config.py`; never use it outside your machine).

**3. Try it:** in the console's Sandbox, send the small, medium and oversized refunds. They should be allowed, held and blocked respectively. Then approve the held one under Approvals.

**Alternative, everything in Docker:**

```bash
docker compose up --build
```

This starts PostgreSQL and the app, with the built console, on http://localhost:8080.

## Configuration

All settings are environment variables (see `backend/approval_loop/config.py`).

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `demo`, `test` or `production` | `demo` |
| `DATABASE_URL` | PostgreSQL connection string. **Required in production.** | unset (in-memory) |
| `DATABASE_SCHEMA` | PostgreSQL schema | `public` |
| `SCHEDULER_API_KEY` | Shared key for operators, admin and the scheduler (`X-API-Key` header) | development value; refused in production |
| `AGENT_IDENTITY_SECRET` | Secret for signing agent tokens | development value; refused in production |
| `REQUIRE_BOUND_AGENT_TOKENS` | Require tokens bound to one request and proposal | on in production, off otherwise |
| `OIDC_AUDIENCE` | Expected audience for Google OIDC tokens. Unset disables OIDC (fail closed). `OIDC_EXPECTED_AUDIENCE` is accepted as an alias. | unset |
| `AGENT_OIDC_BINDINGS` | `agent_id=service-account-email,...` pairs for agent OIDC | empty |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Optional LLM for wording; required in production | unset / `gemini-3.7-flash` |
| `MODEL_ARMOR_ENABLED` / `MODEL_ARMOR_FAIL_CLOSED` | Google Cloud Model Armor screening (needs Google credentials) | `true` / `true` |
| `MODEL_ARMOR_LOCATION` / `MODEL_ARMOR_TEMPLATE_ID` | Model Armor region and template | `us-central1` / `default-guardrail` |
| `APPROVAL_TTL_SECONDS` | How long a held action can still be approved | `86400` (24 h) |
| `ADMIN_FALLBACK_EMAIL` | Escalation target when no backup approver exists | development value |
| `APP_ALLOWED_ORIGINS` | CORS origins (no `*` in production) | localhost origins |
| `ALLOW_INSECURE_DEMO_AUTH` | Allow unauthenticated operator calls outside production | `false` |
| `GOOGLE_CLOUD_PROJECT` | Google Cloud project for OIDC and Model Armor | set in config |

Production start-up is refused if default secrets are used, `DATABASE_URL` or `GEMINI_API_KEY` is missing, insecure demo auth is enabled, or CORS allows `*`.

## API overview

All routes are under `/api`. Interactive documentation is at `/docs` when the server is running.

| Method and path | What it does | Auth |
|---|---|---|
| `POST /gateway/propose` | Submit an agent proposal; returns the decision | agent token |
| `GET /gateway/actions/pending` | Held actions waiting for a person | operator |
| `POST /gateway/actions/{id}/approve` · `/reject` | Decide a held action (body: `{"notes": "..."}`); the approve response includes an explicit `execution` status | operator |
| `GET /memory/workflows` | Workflow history with decisions, reviews and execution results | operator in production |
| `GET /registry/agents` | List agents | operator in production |
| `POST /registry/agents/{id}/status` | Enable or disable an agent | admin |
| `GET /reports` · `GET /actions` | Expense reports and reminder log | operator in production |
| `POST /reports` · `POST /reports/{id}/resolve` | Create or resolve an expense report | operator |
| `POST /tick` | Run the reminder loop (called by Cloud Scheduler) | scheduler |
| `GET /actions/{id}/why-acted` | Explain why the reminder loop acted | **none, even in production** (see limitations) |
| `GET /metrics` · `GET /traces` | Counters and recent traces | operator in production |
| `GET /agbom` | Agent inventory | none |
| `POST /demo/*` · `/seed` · `/simulate-*` | Sandbox scenarios; these endpoints do not exist (404) in production | none |
| `GET /health/live` · `/health/ready` | Health checks (outside `/api`) | none |

## Tests and evaluation

```bash
cd backend
PYTHONPATH=. python -m pytest tests -q
```

The suite has 210 tests. Twelve run against a real PostgreSQL server: set `TEST_DATABASE_URL`, or leave it unset to start an embedded server from the `pgserver` dev dependency. CI runs on Python 3.10 and 3.11 with a PostgreSQL 16 service, builds the console, and builds the Docker image.

`paper/` contains an IEEE-style evaluation with a reproducible harness (`paper/eval/run_evaluation.py`). Measured in-process on a laptop, after the fixes it reports:

- **Speed:** median gateway decision 0.26–0.29 ms; approving one action takes about 0.11 ms whether 100 or 10,000 workflows are stored.
- **Policy:** 20,040 of 20,040 decisions matched the documented limits.
- **Concurrency:** exactly one approval won in all 200 concurrent-approval races.
- **Text filter:** 25 of 34 attacks detected and 0 of 30 normal texts flagged. No undetected attack reached a more permissive outcome than its amount allowed.

These figures exclude network, database and model latency. The attack sets are small and written by the author, and no real LLM was used in the evaluation.

## Deploy to Google Cloud

`deploy.sh` deploys to Cloud Run, connects Cloud SQL for PostgreSQL, and creates a Cloud Scheduler job for `/api/tick`:

```bash
export GOOGLE_CLOUD_PROJECT=your-project
export CLOUD_SQL_INSTANCE=your-project:us-central1:approvalloop
export DATABASE_URL="postgresql://USER:PASSWORD@/approvalloop?host=/cloudsql/$CLOUD_SQL_INSTANCE"
export GEMINI_API_KEY=...
./deploy.sh
```

With `USE_SECRET_MANAGER=true`, secrets are read from Secret Manager (`gemini-api-key`, `scheduler-api-key`, `database-url`) instead of the environment. The GitHub workflow `.github/workflows/deploy.yml` does the same when the `GCP_SA_KEY` and `CLOUD_SQL_INSTANCE` repository secrets are set. Neither path has been run against a real Google Cloud project as part of this work.

## Known limitations

- **Two read endpoints are unauthenticated.** `GET /api/actions/{id}/why-acted` (reminder-action details, including recipients) and `GET /api/agbom` (agent inventory) need no key, even in production.
- **One shared key for people.** Operators, admin and the scheduler share `SCHEDULER_API_KEY`, so decisions are recorded as "Admin Operator (API-Key)" rather than a named person. Production use needs real sign-in (OIDC) in front of the console.
- **Daily cap is per server.** The cap total and the in-memory fallback for replay protection are kept in each process; several API instances need these in the shared database.
- **No real execution.** Approved actions are recorded and "sent" through a mock notifier; no payment, CRM or ticketing system is called.
- **Limited model role.** See [What is real and what is not](#what-is-real-and-what-is-not); making the model choose structured proposals (with the gateway still enforcing limits) is the main open step.
- **Policy limits are duplicated** in the console (`frontend/src/lib/policy.ts`) for display; the server is authoritative.
- **No** multi-tenancy, rate limiting, per-recipient limits or data-retention policy.

## Further reading

- `docs/STUDY_GUIDE.md`: a guided walk through the code, with exercises and a plan for extending it into a real multi-agent system.
- `paper/approvalloop.pdf`: design, evaluation and the defects found and fixed.

## License

No license file has been added yet, so all rights are reserved by default. Add a `LICENSE` file (for example Apache-2.0 or MIT) before others reuse the code.
