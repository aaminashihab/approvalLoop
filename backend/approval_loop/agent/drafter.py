import os
import json
import logging
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field
from approval_loop.domain.models import ActionType
from approval_loop.agent.prompts import build_drafting_prompt
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail

logger = logging.getLogger("approval_loop.drafter")

class DraftProposalResponse(BaseModel):
    """Structured response model for Gemini drafting proposal."""
    message: str = Field(description="Body message text of the notification")
    tone: str = Field(default="professional", description="Tone: polite_nudge | urgent_escalation | professional")
    reasoning: str = Field(default="Contextual communication drafted based on elapsed duration and business state.", description="Language reasoning context")
    references_report: bool = Field(default=True, description="Whether the report is referenced")

class GeminiAgentDrafter:
    """
    Google GenAI SDK Drafter (Google Agent Framework).
    Boundary: LLM proposes language wording and reasoning; deterministic code owns the authoritative business figures.
    """
    def __init__(self, api_key: str | None = None, model: str | None = None, guardrail: Optional[ModelSafetyGuardrail] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.guardrail = guardrail or ModelSafetyGuardrail()
        self.client = None
        if self.api_key:
            try:
                import google.genai as genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning("Could not initialize google.genai client: %s", str(e))
                self.client = None

    def _deterministic_fallback(
        self,
        action_type: ActionType,
        report_id: str,
        submitter: str,
        amount: Decimal,
        currency: str,
        description: str
    ) -> DraftProposalResponse:
        if action_type == ActionType.NUDGE:
            msg = f"Hello, this is a reminder regarding expense report {report_id} submitted by {submitter} for {currency} {amount} ({description}). Please review and sign off when convenient."
            tone = "polite_nudge"
            reasoning = f"Initial follow-up for pending report {report_id}; friendly non-intrusive reminder."
        else:
            msg = f"Hello, this is an automated escalation for expense report {report_id} from {submitter} for {currency} {amount} ({description}). The primary approver has not responded."
            tone = "urgent_escalation"
            reasoning = f"Escalation triggered because primary approver exceeded stale threshold on report {report_id}."

        return DraftProposalResponse(
            message=msg,
            tone=tone,
            reasoning=reasoning,
            references_report=True
        )

    def draft_proposal(
        self,
        action_type: ActionType,
        report_id: str,
        submitter: str,
        amount: Decimal,
        currency: str,
        description: str,
        injected_mock_response: str | None = None,
        hours_pending: float | None = None
    ) -> DraftProposalResponse:
        """Returns the full validated DraftProposalResponse with message, tone, and language reasoning."""
        fallback = self._deterministic_fallback(action_type, report_id, submitter, amount, currency, description)

        # Injected mock takes priority for deterministic test scenarios
        if injected_mock_response:
            return DraftProposalResponse(
                message=injected_mock_response,
                tone="test_injected",
                reasoning="Injected test mock wording",
                references_report=True
            )

        if not self.client:
            return fallback

        prompt = build_drafting_prompt(
            action_type, report_id, submitter, amount, currency, description, hours_pending
        )

        # 1. Pre-LLM Model Armor Prompt Inspection
        safety_prompt = self.guardrail.inspect_prompt(prompt)
        if not safety_prompt.passed:
            logger.warning("GeminiAgentDrafter prompt rejected by Model Armor guardrail: %s", safety_prompt.reason)
            return fallback

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            raw_text = response.text.strip()

            # 2. Post-LLM Model Armor Output Inspection
            safety_out = self.guardrail.inspect_model_output(raw_text, user_prompt=prompt)
            if not safety_out.passed:
                logger.warning("GeminiAgentDrafter output rejected by Model Armor guardrail: %s", safety_out.reason)
                return fallback

            # Clean possible markdown json fences
            clean_json = raw_text
            if clean_json.startswith("```"):
                clean_json = clean_json.split("\n", 1)[-1].rsplit("\n", 1)[0].strip()
                if clean_json.startswith("json"):
                    clean_json = clean_json[4:].strip()
            
            try:
                parsed_data = json.loads(clean_json)
                proposal = DraftProposalResponse.model_validate(parsed_data)
                if not proposal.message or not proposal.message.strip():
                    logger.warning("Empty message in structured response; falling back to deterministic template.")
                    return fallback
                return proposal
            except Exception as parse_err:
                logger.warning(
                    "Structured output validation failed (%s). Malformed JSON/schema rejected; using deterministic fallback.",
                    str(parse_err)
                )
                return fallback

        except Exception as e:
            logger.warning("Gemini generation failed (%s), using resilient fallback template", str(e))
            return fallback

    def draft_wording(
        self,
        action_type: ActionType,
        report_id: str,
        submitter: str,
        amount: Decimal,
        currency: str,
        description: str,
        injected_mock_response: str | None = None,
        hours_pending: float | None = None
    ) -> str:
        """Maintains backward compatibility by returning the validated body text string."""
        proposal = self.draft_proposal(
            action_type=action_type,
            report_id=report_id,
            submitter=submitter,
            amount=amount,
            currency=currency,
            description=description,
            injected_mock_response=injected_mock_response,
            hours_pending=hours_pending
        )
        return proposal.message

