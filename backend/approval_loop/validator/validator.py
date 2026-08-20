from approval_loop.domain.models import (
    ActionRecord, ExpenseReport, ValidatorResultEnum, NotificationEnvelope, ValidatorCheckDetails
)
from approval_loop.domain.state_machine import StateMachine
from approval_loop.domain.registry import ApproverRegistry

class DeterministicValidator:
    """
    4-Point Deterministic Safety Validator:
    Code Disposes: Authoritative verification before any notification leaves the system.
    Note: Idempotency is enforced separately via the preceding Transactional Outbox Claiming Gate.
    """
    def __init__(self, registry: ApproverRegistry):
        self.registry = registry

    def validate(
        self,
        action: ActionRecord,
        report: ExpenseReport,
        envelope: NotificationEnvelope
    ) -> tuple[ValidatorResultEnum, str, ValidatorCheckDetails]:
        checks = ValidatorCheckDetails()

        # 1. Authoritative Recipient Verification against Registry Hierarchy
        if not self.registry.is_authorized(envelope.recipient):
            checks.recipient_verified = False
            return (
                ValidatorResultEnum.BLOCKED,
                f"Recipient '{envelope.recipient}' is not authorized in approver registry.",
                checks
            )

        # 2. Authoritative Report ID Match
        if envelope.report_id != report.report_id or action.report_id != report.report_id:
            checks.report_id_verified = False
            return (
                ValidatorResultEnum.BLOCKED,
                f"Report ID mismatch: envelope '{envelope.report_id}' != report '{report.report_id}'.",
                checks
            )

        # 3. Authoritative Decimal Amount Match
        if envelope.amount != report.amount or action.amount != report.amount:
            checks.amount_verified = False
            return (
                ValidatorResultEnum.BLOCKED,
                f"Amount mismatch: envelope {envelope.amount} != report {report.amount}.",
                checks
            )

        # 4. State Machine Legal Transition Match
        if not StateMachine.is_transition_legal(action.source_state, action.target_state):
            checks.state_verified = False
            return (
                ValidatorResultEnum.BLOCKED,
                f"Illegal state transition: cannot transition from {action.source_state.value} to {action.target_state.value}.",
                checks
            )

        return (ValidatorResultEnum.PASS, "4-point deterministic safety validator passed all checks (recipient, ID, amount, state).", checks)
