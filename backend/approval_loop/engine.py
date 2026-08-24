import uuid
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional
from approval_loop.config import Settings
from approval_loop.storage.base import BaseRepository
from approval_loop.domain.models import (
    ExpenseReport, ActionRecord, ActionType, ReportStatus,
    ValidatorResultEnum, ActionStatus, NotificationEnvelope,
    StateTransitionResult, AutonomyMetrics, utc_now
)
from approval_loop.domain.eligibility import EligibilityEvaluator
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.agent.drafter import GeminiAgentDrafter
from approval_loop.validator.validator import DeterministicValidator
from approval_loop.policy.policy_engine import PolicyEngine, PolicyDecisionEnum
from approval_loop.observability.tracer import OpenTelemetryTracer
from approval_loop.skills.skill_registry import SkillRegistry
from approval_loop.worker.worker import BaseNotificationProvider, MockNotificationWorker

logger = logging.getLogger("approval_loop.engine")

class ApprovalEngine:
    """
    ApprovalLoop Core Autonomous Orchestrator.
    Pipeline: OBSERVE -> DECIDE -> CLAIM -> DRAFT -> VERIFY -> POLICY -> ACT -> TRANSITION -> REPEAT
    """
    def __init__(
        self,
        repo: BaseRepository,
        settings: Settings,
        registry: ApproverRegistry,
        drafter: GeminiAgentDrafter,
        validator: DeterministicValidator,
        worker: BaseNotificationProvider,
        policy_engine: Optional[PolicyEngine] = None,
        tracer: Optional[OpenTelemetryTracer] = None,
        skill_registry: Optional[SkillRegistry] = None
    ):
        self.repo = repo
        self.settings = settings
        self.registry = registry
        self.drafter = drafter
        self.validator = validator
        self.worker = worker
        self.policy_engine = policy_engine or PolicyEngine(settings)
        self.tracer = tracer or OpenTelemetryTracer.get_tracer()
        self.skill_registry = skill_registry or SkillRegistry()

        # Autonomy Metrics Ledger
        self.total_observed = 0
        self.total_eligible = 0
        self.total_claimed = 0
        self.total_sent = 0
        self.total_escalations = 0
        self.total_blocked = 0
        self.total_duplicates_prevented = 0
        self.total_unsafe_transitions_prevented = 0
        self.last_wake_up_time: datetime | None = None

    def get_autonomy_metrics(self) -> AutonomyMetrics:
        actions = self.repo.list_all_actions()
        blocked_count = sum(1 for a in actions if a.status == ActionStatus.BLOCKED)
        escalations_count = sum(1 for a in actions if a.action_type == ActionType.ESCALATE and a.status == ActionStatus.COMPLETED)
        sent_count = sum(1 for a in actions if a.status in (ActionStatus.SENT, ActionStatus.COMPLETED))
        skipped_count = sum(1 for a in actions if a.state_transition and a.state_transition.value == "skipped")

        return AutonomyMetrics(
            last_wake_up=self.last_wake_up_time.isoformat() if self.last_wake_up_time else utc_now().isoformat(),
            reports_observed=max(self.total_observed, len(self.repo.list_all_reports())),
            eligible_reports=self.total_eligible,
            actions_claimed=len(actions),
            notifications_sent=sent_count,
            escalations_count=escalations_count,
            blocked_actions_count=blocked_count,
            duplicate_actions_prevented=self.total_duplicates_prevented,
            unsafe_transitions_prevented=skipped_count,
            human_prompts_required=0
        )

    def run_tick(
        self,
        tick_id: str | None = None,
        current_time: datetime | None = None,
        injected_adversarial_draft: str | None = None,
        injected_adversarial_envelope: NotificationEnvelope | None = None
    ) -> list[ActionRecord]:
        if not tick_id:
            tick_id = f"tick_{uuid.uuid4().hex[:8]}"
        now = current_time or utc_now()
        self.last_wake_up_time = now
        thresholds = self.settings.thresholds
        processed_actions = []

        self.tracer.start_trace("approval.tick", trace_id=f"trace_{tick_id}")

        try:
            # 1. OBSERVE: Scan open expense reports
            with self.tracer.start_span("observe", {"tick_id": tick_id}):
                open_reports = self.repo.list_open_reports()
                self.total_observed += len(open_reports)

            for report in open_reports:
                try:
                    # 2. DECIDE: Deterministic Eligibility
                    with self.tracer.start_span("eligibility", {"report_id": report.report_id}):
                        eval_res = EligibilityEvaluator.evaluate(report, now, thresholds)
                        if not eval_res:
                            continue

                    self.total_eligible += 1
                    action_type, target_state = eval_res

                    if action_type == ActionType.NUDGE:
                        recipient = report.approver_email
                    else:
                        self.total_escalations += 1
                        # Runtime Skill Discovery & Progressive Disclosure for Escalation
                        with self.tracer.start_span("skill.load", {"skill": "approval_escalation", "report_id": report.report_id}):
                            escalation_skill = self.skill_registry.get_skill("approval_escalation")
                            if escalation_skill:
                                logger.debug("Loaded escalation procedural skill: %s", escalation_skill.name)
                            if report.amount >= Decimal("5000.00"):
                                # Progressive disclosure level 2: load reference document for high-value escalation
                                self.skill_registry.load_skill_reference("approval_escalation", "escalation_policy.md")

                        recipient = self.registry.resolve_escalation_recipient(
                            report.approver_email, report.backup_approver_email
                        )

                    idempotency_key = f"{report.report_id}:{action_type.value}"

                    candidate_action = ActionRecord(
                        report_id=report.report_id,
                        action_type=action_type,
                        source_state=report.status,
                        target_state=target_state,
                        tick_id=tick_id,
                        idempotency_key=idempotency_key,
                        recipient=recipient,
                        amount=report.amount,
                    )

                    # 3. ATOMIC OUTBOX CLAIM — Prevents duplicate runs & race collisions
                    with self.tracer.start_span("claim", {"report_id": report.report_id, "idempotency_key": idempotency_key}):
                        claimed, claim_msg, active_action = self.repo.claim_action_transaction(candidate_action)
                        if not claimed or not active_action:
                            self.total_duplicates_prevented += 1
                            continue

                    self.total_claimed += 1

                    # 4. GEMINI DRAFTER — Language Wording Only
                    with self.tracer.start_span("gemini.draft", {"report_id": report.report_id, "model": self.drafter.model}):
                        hours_pending = (now - report.submitted_at).total_seconds() / 3600.0
                        wording = self.drafter.draft_wording(
                            action_type=action_type,
                            report_id=report.report_id,
                            submitter=report.submitter_name,
                            amount=report.amount,
                            currency=report.currency,
                            description=report.description,
                            injected_mock_response=injected_adversarial_draft,
                            hours_pending=hours_pending
                        )
                        active_action.message = wording

                    # 5. ASSEMBLE AUTHORITATIVE ENVELOPE (Code owns business truth)
                    if injected_adversarial_envelope:
                        envelope = injected_adversarial_envelope
                    else:
                        subject = (
                            f"Action Required: Expense Report {report.report_id}"
                            if action_type == ActionType.NUDGE
                            else f"ESCALATION: Stalled Expense Report {report.report_id}"
                        )
                        envelope = NotificationEnvelope(
                            report_id=report.report_id,
                            amount=report.amount,
                            currency=report.currency,
                            recipient=recipient,
                            submitter_name=report.submitter_name,
                            subject=subject,
                            body_text=wording,
                            raw_llm_draft=wording
                        )
                    active_action.envelope = envelope

                    # 6. VERIFY: 4-Point Deterministic Safety Validator Gate
                    with self.tracer.start_span("validation", {"report_id": report.report_id}):
                        v_res, v_reason, v_checks = self.validator.validate(active_action, report, envelope)
                        active_action.validator_result = v_res
                        active_action.validator_reason = v_reason
                        active_action.validator_checks = v_checks

                    if v_res == ValidatorResultEnum.BLOCKED:
                        self.total_blocked += 1
                        active_action.status = ActionStatus.BLOCKED
                        self.repo.save_action(active_action)
                        processed_actions.append(active_action)
                        continue

                    # 7. POLICY CHECK: Corporate Governance Policy Engine
                    with self.tracer.start_span("policy.check", {"report_id": report.report_id}):
                        p_res, p_reason = self.policy_engine.evaluate(active_action, report, envelope)
                        if p_res == PolicyDecisionEnum.DENY:
                            self.total_blocked += 1
                            active_action.status = ActionStatus.BLOCKED
                            active_action.validator_result = ValidatorResultEnum.BLOCKED
                            active_action.validator_reason = p_reason
                            self.repo.save_action(active_action)
                            processed_actions.append(active_action)
                            continue

                    # 7.5. FINAL PRE-DISPATCH STATE CHECK: Prevent stale notifications if state changed in-flight
                    with self.tracer.start_span("pre_dispatch_check", {"report_id": report.report_id}):
                        fresh_report = self.repo.get_report(report.report_id)
                        if not fresh_report or fresh_report.status != active_action.source_state:
                            logger.info(
                                "Pre-dispatch check: report %s status changed (expected %s, found %s). Skipping notification dispatch.",
                                report.report_id,
                                active_action.source_state.value,
                                fresh_report.status.value if fresh_report else "DELETED"
                            )
                            active_action.status = ActionStatus.COMPLETED
                            active_action.state_transition = StateTransitionResult.SKIPPED
                            active_action.skip_reason = f"report state changed before transition commit (expected={active_action.source_state.value}, found={fresh_report.status.value if fresh_report else 'DELETED'})"
                            active_action.completed_at = utc_now()
                            self.repo.save_action(active_action)
                            self.total_unsafe_transitions_prevented += 1
                            processed_actions.append(active_action)
                            continue

                    # 8. ACT: Notification Worker Dispatch
                    with self.tracer.start_span("notification", {"recipient": envelope.recipient, "report_id": report.report_id}):
                        delivery_ok, notif_id, err = self.worker.send(envelope, idempotency_key=active_action.idempotency_key)
                        if not delivery_ok:
                            failed_action = self.repo.mark_failed(active_action.action_id, err or "Delivery failed")
                            processed_actions.append(failed_action)
                            continue

                    active_action.sent_at = utc_now()
                    active_action.notification_id = notif_id
                    active_action.status = ActionStatus.SENT
                    self.total_sent += 1

                    # 9. CONDITIONAL STATE TRANSITION: Race-Safe Invariant
                    with self.tracer.start_span("state_transition", {"report_id": report.report_id}):
                        completed_action = self.repo.apply_conditional_transition(active_action.action_id)
                        if completed_action.state_transition and completed_action.state_transition.value == "skipped":
                            self.total_unsafe_transitions_prevented += 1

                    processed_actions.append(completed_action)

                except Exception as e:
                    logger.exception("Isolated failure on report %s during tick %s: %s", getattr(report, 'report_id', 'unknown'), tick_id, str(e))

        finally:
            self.tracer.end_trace()

        return processed_actions
