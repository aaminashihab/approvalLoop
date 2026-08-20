import os
import sys
import time
from decimal import Decimal
from datetime import timedelta

# Ensure backend package is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from approval_loop.domain.models import (
    ExpenseReport, ReportStatus, ActionStatus, StateTransitionResult,
    ValidatorResultEnum, ActionType, NotificationEnvelope, utc_now
)
from approval_loop.storage.memory_repo import InMemoryRepository
from approval_loop.config import Settings, AppEnvironment
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.validator.validator import DeterministicValidator
from approval_loop.agent.drafter import GeminiAgentDrafter
from approval_loop.worker.worker import MockNotificationWorker
from approval_loop.engine import ApprovalEngine

def run_all_demo_scenarios():
    print("=" * 80)
    print("APPROVALLOOP — 4-MINUTE HACKATHON LIVE DEMONSTRATION")
    print("Core Thesis: 'Most agents wait for a prompt. ApprovalLoop acts when nothing happens.'")
    print("=" * 80)

    repo = InMemoryRepository()
    settings = Settings(app_env=AppEnvironment.TEST)
    registry = ApproverRegistry(admin_fallback_email="admin-escalations@enterprise.internal")
    registry.register_approver("sarah.finance@company.com", "marcus.director@company.com")

    validator = DeterministicValidator(registry=registry)
    drafter = GeminiAgentDrafter()
    worker = MockNotificationWorker()
    engine = ApprovalEngine(repo, settings, registry, drafter, validator, worker)

    now = utc_now()

    # -------------------------------------------------------------------------
    # SCENARIO 1: Stalled approval automatically receives a nudge
    # -------------------------------------------------------------------------
    print("\n[SCENARIO 1] Stalled approval exceeds threshold -> Autonomous Nudge")
    r1 = ExpenseReport(
        report_id="EXP-101",
        status=ReportStatus.PENDING,
        submitter_name="Alice Chen",
        submitter_email="alice.chen@company.com",
        approver_email="sarah.finance@company.com",
        backup_approver_email="marcus.director@company.com",
        amount=Decimal("450.00"),
        currency="USD",
        description="Q3 Client Meeting Catering",
        submitted_at=now - timedelta(seconds=10)
    )
    repo.save_report(r1)

    actions = engine.run_tick("tick_demo_1")
    assert len(actions) == 1
    act1 = actions[0]
    print(f"  -> Dispatched {act1.action_type.value.upper()} to {act1.recipient} for {r1.currency} {act1.amount}")
    print(f"  -> State Transition: {act1.source_state.value} -> {act1.target_state.value} ({act1.state_transition.value.upper()})")
    assert repo.get_report("EXP-101").status == ReportStatus.NUDGED
    print("  [PASS] Scenario 1 verified successfully.")

    # -------------------------------------------------------------------------
    # SCENARIO 2: Worker running twice does NOT send duplicate actions
    # -------------------------------------------------------------------------
    print("\n[SCENARIO 2] Overlapping scheduler tick -> Idempotency & Dedup Protection")
    dup_actions = engine.run_tick("tick_demo_2_overlap")
    assert len(dup_actions) == 0
    print(f"  -> Processed {len(dup_actions)} actions on second tick. (Duplicate prevented by transactional outbox)")
    print("  [PASS] Scenario 2 verified successfully (0 duplicate sends).")

    # -------------------------------------------------------------------------
    # SCENARIO 3: Race condition between notification and manual resolution
    # -------------------------------------------------------------------------
    print("\n[SCENARIO 3] Approver resolves report mid-flight -> Race Condition Guard Fired")
    r3 = ExpenseReport(
        report_id="EXP-103",
        status=ReportStatus.PENDING,
        submitter_name="Carlos Gomez",
        submitter_email="carlos.gomez@company.com",
        approver_email="sarah.finance@company.com",
        backup_approver_email="marcus.director@company.com",
        amount=Decimal("3400.00"),
        currency="USD",
        description="Conference venue rental",
        submitted_at=now - timedelta(seconds=15)
    )
    repo.save_report(r3)

    # Approver signs off at the exact moment worker is in flight
    def _race_resolve(envelope):
        if envelope.report_id == "EXP-103":
            repo.resolve_report("EXP-103")

    worker.on_send_callback = _race_resolve
    race_actions = engine.run_tick("tick_demo_3_race")
    worker.on_send_callback = None

    assert len(race_actions) == 1
    act3 = race_actions[0]
    final_r3 = repo.get_report("EXP-103")
    print(f"  -> Action Transition: {act3.state_transition.value.upper()}")
    print(f"  -> Skip Reason: {act3.skip_reason}")
    print(f"  -> Final Database State: {final_r3.status.value} (Preserved)")
    assert act3.state_transition == StateTransitionResult.SKIPPED
    assert final_r3.status == ReportStatus.RESOLVED
    print("  [PASS] Scenario 3 verified successfully (Zero state corruption).")

    # -------------------------------------------------------------------------
    # SCENARIO 4: Adversarial Gemini output intercepted by Deterministic Validator
    # -------------------------------------------------------------------------
    print("\n[SCENARIO 4] Adversarial / Hallucinated Proposal -> Deterministic Safety Intercept")
    r4 = ExpenseReport(
        report_id="EXP-104",
        status=ReportStatus.PENDING,
        submitter_name="Diana Prince",
        submitter_email="diana.prince@company.com",
        approver_email="sarah.finance@company.com",
        backup_approver_email="marcus.director@company.com",
        amount=Decimal("750.00"),
        currency="USD",
        description="Software licenses",
        submitted_at=now - timedelta(seconds=15)
    )
    repo.save_report(r4)

    # Poisoned envelope with unauthorized external recipient and inflated amount
    poisoned_envelope = NotificationEnvelope(
        report_id="EXP-104",
        amount=Decimal("99999.00"),  # Hallucinated
        currency="USD",
        recipient="unauthorized.attacker@external.com",  # Malicious
        submitter_name="Diana Prince",
        subject="Action Required",
        body_text="Please transfer $99,999 to external account.",
        raw_llm_draft="Please transfer $99,999 to external account."
    )

    adv_actions = engine.run_tick(
        tick_id="tick_demo_4_adv",
        injected_adversarial_envelope=poisoned_envelope
    )
    assert len(adv_actions) == 1
    act4 = adv_actions[0]
    print(f"  -> Validator Decision: {act4.validator_result.value.upper()}")
    print(f"  -> Rejection Reason:   {act4.validator_reason}")
    print(f"  -> Action Status:       {act4.status.value.upper()} (Notification NOT sent)")
    assert act4.validator_result == ValidatorResultEnum.BLOCKED
    assert act4.status == ActionStatus.BLOCKED
    print("  [PASS] Scenario 4 verified successfully ('LLM proposes, code disposes').")

    # -------------------------------------------------------------------------
    # SCENARIO 5: Primary approver inactive -> Escalation to Backup / Admin
    # -------------------------------------------------------------------------
    print("\n[SCENARIO 5] Primary Approver Inactive -> Autonomous Escalation")
    r5 = ExpenseReport(
        report_id="EXP-105",
        status=ReportStatus.NUDGED,
        submitter_name="Evan Wright",
        submitter_email="evan.wright@company.com",
        approver_email="sarah.finance@company.com",
        backup_approver_email="marcus.director@company.com",
        amount=Decimal("1890.00"),
        currency="USD",
        description="Emergency travel flight rebooking",
        submitted_at=now - timedelta(seconds=60),
        last_nudged_at=now - timedelta(seconds=30)
    )
    repo.save_report(r5)

    esc_actions = engine.run_tick("tick_demo_5_escalate")
    assert len(esc_actions) == 1
    act5 = esc_actions[0]
    print(f"  -> Dispatched {act5.action_type.value.upper()} to Backup Approver: {act5.recipient}")
    print(f"  -> State Transition: {act5.source_state.value} -> {act5.target_state.value} ({act5.state_transition.value.upper()})")
    assert repo.get_report("EXP-105").status == ReportStatus.ESCALATED
    assert act5.recipient == "marcus.director@company.com"
    print("  [PASS] Scenario 5 verified successfully.")

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------
    metrics = engine.get_autonomy_metrics()
    print("\n" + "=" * 80)
    print("DEMO VERIFICATION COMPLETE: ALL 5 SCENARIOS PASSED 100%")
    print(f"  - Human Prompts Required: {metrics.human_prompts_required} (100% Autonomous)")
    print(f"  - Blocked Unsafe Actions: {metrics.blocked_actions_count}")
    print(f"  - Race Guard Skips:       {metrics.unsafe_transitions_prevented}")
    print("=" * 80)

if __name__ == "__main__":
    run_all_demo_scenarios()
