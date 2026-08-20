from typing import Optional

class ApproverRegistry:
    """Trusted approver and escalation hierarchy registry."""
    def __init__(self, admin_fallback_email: str):
        self.admin_fallback_email = admin_fallback_email
        self._approvers: dict[str, Optional[str]] = {}  # approver_email -> backup_approver_email

    def register_approver(self, approver_email: str, backup_approver_email: Optional[str] = None):
        self._approvers[approver_email] = backup_approver_email

    def is_authorized(self, email: str) -> bool:
        if email == self.admin_fallback_email:
            return True
        if email in self._approvers:
            return True
        if any(backup == email for backup in self._approvers.values() if backup):
            return True
        return False

    def resolve_escalation_recipient(self, approver_email: str, explicit_backup: Optional[str] = None) -> str:
        if explicit_backup:
            return explicit_backup
        backup = self._approvers.get(approver_email)
        if backup:
            return backup
        return self.admin_fallback_email
