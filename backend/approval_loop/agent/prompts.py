from decimal import Decimal
from typing import Optional
from approval_loop.domain.models import ActionType

SYSTEM_INSTRUCTIONS = """You are the drafting communication assistant for ApprovalLoop, an autonomous corporate approval chaser.
Your task is to draft a concise, polite, and professional notification for an expense sign-off action.

Rules:
1. Provide a polite, direct reminder.
2. Mention the Report ID and Submitter.
3. If this is an ESCALATION, clearly note that the primary approver did not respond.
4. Output a JSON object with:
   - "message": The clean email body text.
   - "tone": "professional"
   - "references_report": true
"""

def build_drafting_prompt(
    action_type: ActionType,
    report_id: str,
    submitter: str,
    amount: Decimal,
    currency: str,
    description: str,
    hours_pending: Optional[float] = None
) -> str:
    """
    Dynamic context assembly without bloated RAG:
    Separates static system instructions from dynamic workflow state.
    """
    dynamic_context = f"""[Dynamic Execution Context]
- Action Type: {action_type.value.upper()}
- Expense Report ID: {report_id}
- Submitter Name: {submitter}
- Authoritative Amount: {currency} {amount}
- Description: {description}
- Stalled Duration: {f'{hours_pending:.1f} hours' if hours_pending is not None else 'Overdue'}
"""
    return f"{SYSTEM_INSTRUCTIONS}\n{dynamic_context}\nReturn valid JSON only:"
