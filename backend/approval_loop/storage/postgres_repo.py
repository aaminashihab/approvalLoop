"""
PostgreSQL storage backend.

Behaviour mirrors InMemoryRepository (the reference implementation used by most tests), with the
database providing the atomicity that the in-memory version gets from a process lock:

* claims and state transitions lock the rows they read (SELECT ... FOR UPDATE) inside one transaction;
* the human-approval claim is a single conditional UPDATE (... WHERE state = expected), so exactly one
  caller wins even across many API instances.

Records are returned as fresh objects. Callers must save a record after changing it; nothing is
persisted by mutating an object in place.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from approval_loop.domain.models import (
    ActionRecord, ActionStatus, ExpenseReport, ReportStatus, StateTransitionResult, utc_now,
)
from approval_loop.storage.base import BaseRepository

SCHEMA_SQL = (Path(__file__).with_name("postgres_schema.sql")).read_text(encoding="utf-8")
_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _jsonb(record: Any) -> Jsonb:
    data = record.to_dict() if hasattr(record, "to_dict") else record.model_dump(mode="json")
    return Jsonb(data, dumps=lambda obj: json.dumps(obj, default=str))


def _workflow_model():
    from approval_loop.memory.memory_bank import WorkflowMemoryRecord
    return WorkflowMemoryRecord


def _agent_model():
    from approval_loop.domain.agent_registry import AgentRegistration
    return AgentRegistration


def _task_model():
    from approval_loop.runtime.async_runtime import AsyncTaskRecord
    return AsyncTaskRecord


class PostgresRepository(BaseRepository):
    def __init__(self, dsn: str, schema: str = "public", min_size: int = 1, max_size: int = 10):
        if not _IDENT.match(schema):
            raise ValueError(f"Invalid schema name: {schema!r}")
        self.schema = schema
        self.pool = ConnectionPool(
            dsn, min_size=min_size, max_size=max_size, open=True,
            kwargs={"row_factory": dict_row, "options": f"-c search_path={schema}"},
        )
        with self.pool.connection() as conn:
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.pool.close()

    # ------------------------------------------------------------------ expense reports
    def get_report(self, report_id: str) -> ExpenseReport | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT data FROM expense_reports WHERE report_id = %s", (report_id,)).fetchone()
        return ExpenseReport(**row["data"]) if row else None

    def list_open_reports(self) -> list[ExpenseReport]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT data FROM expense_reports WHERE status <> %s",
                                (ReportStatus.RESOLVED.value,)).fetchall()
        return [ExpenseReport(**r["data"]) for r in rows]

    def list_all_reports(self) -> list[ExpenseReport]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT data FROM expense_reports").fetchall()
        return [ExpenseReport(**r["data"]) for r in rows]

    def _put_report(self, conn, report: ExpenseReport) -> None:
        conn.execute(
            """INSERT INTO expense_reports (report_id, status, data) VALUES (%s, %s, %s)
               ON CONFLICT (report_id) DO UPDATE SET status = EXCLUDED.status, data = EXCLUDED.data""",
            (report.report_id, report.status.value, _jsonb(report)),
        )

    def save_report(self, report: ExpenseReport):
        with self.pool.connection() as conn:
            self._put_report(conn, report)

    def resolve_report(self, report_id: str) -> ExpenseReport | None:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute("SELECT data FROM expense_reports WHERE report_id = %s FOR UPDATE",
                               (report_id,)).fetchone()
            if not row:
                return None
            report = ExpenseReport(**row["data"])
            report.status = ReportStatus.RESOLVED
            report.resolved_at = utc_now()
            self._put_report(conn, report)
            return report

    # ------------------------------------------------------------------ actions
    def _put_action(self, conn, action: ActionRecord) -> None:
        conn.execute(
            """INSERT INTO approval_actions (action_id, created_at, data) VALUES (%s, %s, %s)
               ON CONFLICT (action_id) DO UPDATE SET data = EXCLUDED.data""",
            (action.action_id, action.created_at, _jsonb(action)),
        )

    def claim_action_transaction(self, action: ActionRecord) -> tuple[bool, str, ActionRecord | None]:
        with self.pool.connection() as conn, conn.transaction():
            # Locking the report row serialises every claim for this report (idempotency keys are per report).
            row = conn.execute("SELECT data FROM expense_reports WHERE report_id = %s FOR UPDATE",
                               (action.report_id,)).fetchone()
            if not row:
                return False, f"Report {action.report_id} not found", None
            report = ExpenseReport(**row["data"])
            if report.status != action.source_state:
                return False, (f"Report state changed (expected {action.source_state.value}, "
                               f"found {report.status.value})"), None

            now = utc_now()
            claim = conn.execute(
                """SELECT a.data FROM action_claims c JOIN approval_actions a ON a.action_id = c.action_id
                   WHERE c.idempotency_key = %s FOR UPDATE OF a""",
                (action.idempotency_key,),
            ).fetchone()
            if claim:
                existing = ActionRecord(**claim["data"])
                if existing.status in (ActionStatus.COMPLETED, ActionStatus.SENT):
                    return False, f"Action {action.idempotency_key} already completed", None
                if existing.status == ActionStatus.BLOCKED:
                    return False, f"Action {action.idempotency_key} was terminally BLOCKED by validator", None
                if existing.status in (ActionStatus.CLAIMED, ActionStatus.PROCESSING):
                    if existing.claimed_at and (now - existing.claimed_at) < timedelta(seconds=60):
                        return False, f"Action {action.idempotency_key} is currently in-flight", None
                if existing.status == ActionStatus.FAILED:
                    if existing.attempt_count >= existing.max_attempts:
                        return False, (f"Action {action.idempotency_key} exceeded max_attempts "
                                       f"({existing.max_attempts})"), None
                    if existing.next_attempt_at and now < existing.next_attempt_at:
                        return False, f"Action {action.idempotency_key} retry backoff not elapsed yet", None
                    existing.status = ActionStatus.PROCESSING
                    existing.claimed_at = now
                    self._put_action(conn, existing)
                    return True, "Retry claim acquired", existing

            action.claimed_at = now
            action.status = ActionStatus.PROCESSING
            self._put_action(conn, action)
            conn.execute(
                """INSERT INTO action_claims (idempotency_key, action_id) VALUES (%s, %s)
                   ON CONFLICT (idempotency_key) DO UPDATE SET action_id = EXCLUDED.action_id""",
                (action.idempotency_key, action.action_id),
            )
            return True, "Claim committed", action

    def mark_failed(self, action_id: str, error_msg: str, backoff_seconds: int = 10) -> ActionRecord:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute("SELECT data FROM approval_actions WHERE action_id = %s FOR UPDATE",
                               (action_id,)).fetchone()
            if not row:
                raise KeyError(action_id)
            action = ActionRecord(**row["data"])
            action.status = ActionStatus.FAILED
            action.attempt_count += 1
            action.last_error = error_msg
            action.next_attempt_at = utc_now() + timedelta(seconds=backoff_seconds * (2 ** (action.attempt_count - 1)))
            self._put_action(conn, action)
            return action

    def save_action(self, action: ActionRecord):
        with self.pool.connection() as conn:
            self._put_action(conn, action)

    def get_action(self, action_id: str) -> ActionRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT data FROM approval_actions WHERE action_id = %s", (action_id,)).fetchone()
        return ActionRecord(**row["data"]) if row else None

    def list_all_actions(self) -> list[ActionRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT data FROM approval_actions ORDER BY created_at DESC").fetchall()
        return [ActionRecord(**r["data"]) for r in rows]

    def apply_conditional_transition(self, action_id: str) -> ActionRecord:
        with self.pool.connection() as conn, conn.transaction():
            arow = conn.execute("SELECT data FROM approval_actions WHERE action_id = %s FOR UPDATE",
                                (action_id,)).fetchone()
            if not arow:
                raise KeyError(action_id)
            action = ActionRecord(**arow["data"])
            rrow = conn.execute("SELECT data FROM expense_reports WHERE report_id = %s FOR UPDATE",
                                (action.report_id,)).fetchone()
            if not rrow:
                raise KeyError(action.report_id)
            report = ExpenseReport(**rrow["data"])

            now = utc_now()
            if report.status == action.source_state:
                report.status = action.target_state
                if action.target_state == ReportStatus.NUDGED:
                    report.last_nudged_at = now
                elif action.target_state == ReportStatus.ESCALATED:
                    report.escalated_at = now
                self._put_report(conn, report)
                action.state_transition = StateTransitionResult.APPLIED
            else:
                action.state_transition = StateTransitionResult.SKIPPED
                action.skip_reason = (f"report state changed before transition commit "
                                      f"(expected={action.source_state.value}, found={report.status.value})")
            action.status = ActionStatus.COMPLETED
            action.completed_at = now
            self._put_action(conn, action)
            return action

    # ------------------------------------------------------------------ agent registry
    def save_agent_registration(self, agent: Any):
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO agent_registry (agent_id, data) VALUES (%s, %s)
                   ON CONFLICT (agent_id) DO UPDATE SET data = EXCLUDED.data""",
                (agent.agent_id, _jsonb(agent)),
            )

    def get_agent_registration(self, agent_id: str) -> Any | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT data FROM agent_registry WHERE agent_id = %s", (agent_id,)).fetchone()
        return _agent_model()(**row["data"]) if row else None

    def list_agent_registrations(self) -> list[Any]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT data FROM agent_registry ORDER BY agent_id").fetchall()
        model = _agent_model()
        return [model(**r["data"]) for r in rows]

    # ------------------------------------------------------------------ memory bank
    @staticmethod
    def _state_of(record: Any) -> str:
        st = getattr(record, "state", None)
        return getattr(st, "value", str(st))

    @staticmethod
    def _action_ids_of(record: Any) -> set[str]:
        ids = {getattr(record, "current_action_id", None)}
        approval = getattr(record, "approval_record", None)
        ids.add(getattr(approval, "action_id", None))
        meta = getattr(record, "metadata", None) or {}
        ids.add((meta.get("pending_action") or {}).get("action_id"))
        return {i for i in ids if i}

    def _index_action_ids(self, conn, record: Any) -> None:
        for aid in self._action_ids_of(record):
            conn.execute(
                """INSERT INTO workflow_action_ids (action_id, workflow_id) VALUES (%s, %s)
                   ON CONFLICT (action_id) DO UPDATE SET workflow_id = EXCLUDED.workflow_id""",
                (aid, record.workflow_id),
            )

    def save_workflow_memory(self, record: Any):
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                """INSERT INTO workflow_memories (workflow_id, agent_id, state, updated_at, data)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (workflow_id) DO UPDATE SET agent_id = EXCLUDED.agent_id, state = EXCLUDED.state,
                       updated_at = EXCLUDED.updated_at, data = EXCLUDED.data""",
                (record.workflow_id, record.agent_id, self._state_of(record), record.updated_at, _jsonb(record)),
            )
            self._index_action_ids(conn, record)

    def get_workflow_memory(self, workflow_id: str) -> Any | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT data FROM workflow_memories WHERE workflow_id = %s", (workflow_id,)).fetchone()
        return _workflow_model()(**row["data"]) if row else None

    def list_workflow_memories(self, agent_id: Optional[str] = None, state: Optional[str] = None) -> list[Any]:
        clauses, params = [], []
        if agent_id:
            clauses.append("agent_id = %s")
            params.append(agent_id)
        if state:
            clauses.append("state = %s")
            params.append(state)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.pool.connection() as conn:
            rows = conn.execute(f"SELECT data FROM workflow_memories {where} ORDER BY updated_at", params).fetchall()
        model = _workflow_model()
        return [model(**r["data"]) for r in rows]

    def find_workflow_memory_by_action_id(self, action_id: str) -> Any | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """SELECT w.data FROM workflow_action_ids i JOIN workflow_memories w ON w.workflow_id = i.workflow_id
                   WHERE i.action_id = %s""",
                (action_id,),
            ).fetchone()
        return _workflow_model()(**row["data"]) if row else None

    def compare_and_set_workflow_memory(self, record: Any, expected_state: str) -> bool:
        with self.pool.connection() as conn, conn.transaction():
            cur = conn.execute(
                """UPDATE workflow_memories SET state = %s, updated_at = %s, data = %s
                   WHERE workflow_id = %s AND state = %s""",
                (self._state_of(record), record.updated_at, _jsonb(record), record.workflow_id, expected_state),
            )
            if cur.rowcount != 1:
                return False
            self._index_action_ids(conn, record)
            return True

    # ------------------------------------------------------------------ async tasks
    def save_async_task(self, task: Any):
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO async_tasks (task_id, status, idempotency_key, created_at, data)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (task_id) DO UPDATE SET status = EXCLUDED.status, data = EXCLUDED.data""",
                (task.task_id, str(task.status), task.idempotency_key or None, task.created_at, _jsonb(task)),
            )

    def get_async_task(self, task_id: str) -> Any | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT data FROM async_tasks WHERE task_id = %s", (task_id,)).fetchone()
        return _task_model()(**row["data"]) if row else None

    def get_async_task_by_idempotency_key(self, idempotency_key: str) -> Any | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT data FROM async_tasks WHERE idempotency_key = %s",
                               (idempotency_key,)).fetchone()
        return _task_model()(**row["data"]) if row else None

    def list_async_tasks(self, status: Optional[str] = None) -> list[Any]:
        with self.pool.connection() as conn:
            if status:
                rows = conn.execute("SELECT data FROM async_tasks WHERE status = %s ORDER BY created_at DESC",
                                    (status,)).fetchall()
            else:
                rows = conn.execute("SELECT data FROM async_tasks ORDER BY created_at DESC").fetchall()
        model = _task_model()
        return [model(**r["data"]) for r in rows]
