import os
import tempfile
from decimal import Decimal
from datetime import timedelta
from approval_loop.skills.skill_registry import SkillRegistry
from approval_loop.domain.models import ExpenseReport, ReportStatus, utc_now
from approval_loop.storage.memory_repo import InMemoryRepository
from approval_loop.config import Settings, AppEnvironment
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.validator.validator import DeterministicValidator
from approval_loop.agent.drafter import GeminiAgentDrafter
from approval_loop.worker.worker import MockNotificationWorker
from approval_loop.engine import ApprovalEngine

def test_skill_manifest_and_progressive_disclosure():
    skill_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "skills", "approval_escalation"))
    skill_file = os.path.join(skill_dir, "SKILL.md")
    ref_file = os.path.join(skill_dir, "references", "escalation_policy.md")

    assert os.path.exists(skill_file), "SKILL.md must exist in skills/approval_escalation/"
    assert os.path.exists(ref_file), "escalation_policy.md must exist in skills/approval_escalation/references/"

    with open(skill_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "name: approval_escalation" in content
    assert "trigger_conditions:" in content
    assert "when_not_to_trigger:" in content
    assert "CRITICAL BOUNDARY" in content

def test_skill_registry_loader():
    registry = SkillRegistry()
    skill = registry.get_skill("approval_escalation")
    assert skill is not None
    assert skill.name == "approval_escalation"
    assert len(skill.trigger_conditions) == 3
    assert len(skill.when_not_to_trigger) == 3
    assert "An expense report or access request exceeds its initial nudge SLA threshold." in skill.trigger_conditions
    assert "The expense report is still within its initial review SLA window (fresh)." in skill.when_not_to_trigger

    # Level 2 progressive disclosure
    ref_content = registry.load_skill_reference("approval_escalation", "escalation_policy.md")
    assert ref_content is not None
    assert "Corporate Approval Escalation Policy Reference" in ref_content

def test_skill_yaml_section_parser_with_word_not_in_trigger():
    """Verify that legitimate triggers containing words like 'not' or 'never' are not misclassified."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_skill_dir = os.path.join(tmpdir, "custom_skill")
        os.makedirs(test_skill_dir)
        skill_path = os.path.join(test_skill_dir, "SKILL.md")
        
        content = """---
name: custom_skill
description: Custom skill for testing section parser
trigger_conditions:
  - Primary approver has not responded within SLA.
  - Expense is not resolved yet.
  - Submitter did not provide receipt.
when_not_to_trigger:
  - Expense was already cancelled.
  - Approval is completed.
---
# Skill Body
"""
        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(content)

        registry = SkillRegistry(skills_dir=tmpdir)
        skill = registry.get_skill("custom_skill")
        assert skill is not None
        assert len(skill.trigger_conditions) == 3
        assert len(skill.when_not_to_trigger) == 2
        assert "Primary approver has not responded within SLA." in skill.trigger_conditions
        assert "Expense is not resolved yet." in skill.trigger_conditions
        assert "Submitter did not provide receipt." in skill.trigger_conditions
        assert "Expense was already cancelled." in skill.when_not_to_trigger
        assert "Approval is completed." in skill.when_not_to_trigger

def test_skill_runtime_loading_during_escalation_workflow():
    repo = InMemoryRepository()
    settings = Settings(app_env=AppEnvironment.TEST)
    approver_reg = ApproverRegistry(admin_fallback_email="admin@company.com")
    approver_reg.register_approver("sarah.finance@company.com", "marcus.director@company.com")
    validator = DeterministicValidator(registry=approver_reg)
    drafter = GeminiAgentDrafter()
    worker = MockNotificationWorker()
    skill_registry = SkillRegistry()

    engine = ApprovalEngine(
        repo=repo,
        settings=settings,
        registry=approver_reg,
        drafter=drafter,
        validator=validator,
        worker=worker,
        skill_registry=skill_registry
    )

    now = utc_now()
    r = ExpenseReport(
        report_id="EXP-SKILL-01",
        status=ReportStatus.NUDGED,
        submitter_name="Elena",
        submitter_email="elena@company.com",
        approver_email="sarah.finance@company.com",
        backup_approver_email="marcus.director@company.com",
        amount=Decimal("6500.00"),  # High value triggers progressive disclosure ref
        description="Enterprise annual contract",
        submitted_at=now - timedelta(seconds=60),
        last_nudged_at=now - timedelta(seconds=30)
    )
    repo.save_report(r)

    actions = engine.run_tick("tick_skill_test")
    assert len(actions) == 1
    assert actions[0].action_type.value == "escalate"

    # Verify skill was accessed and cached in registry
    assert "approval_escalation" in skill_registry._skills_cache
