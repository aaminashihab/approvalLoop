-- ApprovalLoop PostgreSQL schema. Idempotent: safe to run on every start-up.
-- Each entity is one row: columns that are filtered, joined or locked on are real (indexed) columns,
-- and the full record is kept in `data` (JSONB) so the Python models stay the single source of shape.

CREATE TABLE IF NOT EXISTS expense_reports (
    report_id   TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    data        JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS expense_reports_status_idx ON expense_reports (status);

CREATE TABLE IF NOT EXISTS approval_actions (
    action_id   TEXT PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL,
    data        JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS approval_actions_created_idx ON approval_actions (created_at DESC);

-- One row per logical action ("{report_id}:{action_type}"): the duplicate-dispatch guard.
CREATE TABLE IF NOT EXISTS action_claims (
    idempotency_key TEXT PRIMARY KEY,
    action_id       TEXT NOT NULL REFERENCES approval_actions (action_id)
);

CREATE TABLE IF NOT EXISTS agent_registry (
    agent_id    TEXT PRIMARY KEY,
    data        JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_memories (
    workflow_id TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    state       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    data        JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS workflow_memories_state_idx ON workflow_memories (state);
CREATE INDEX IF NOT EXISTS workflow_memories_agent_idx ON workflow_memories (agent_id);

-- Every action id a workflow is known by (current, approval record, pending action): indexed lookup for approvals.
CREATE TABLE IF NOT EXISTS workflow_action_ids (
    action_id   TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflow_memories (workflow_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS async_tasks (
    task_id         TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL,
    data            JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS async_tasks_status_idx ON async_tasks (status, created_at DESC);
