import os
import json
import logging
from decimal import Decimal
from pydantic import BaseModel, Field
from approval_loop.domain.models import ActionType
from approval_loop.agent.prompts import build_drafting_prompt

logger = logging.getLogger("approval_loop.drafter")

class DraftProposalResponse(BaseModel):
    """Structured response model for Gemini drafting proposal."""
    message: str = Field(description="Body message text of the notification")
    tone: str = Field(default="professional", description="Tone of the communication")
    references_report: bool = Field(default=True, description="Whether the report is referenced")

class GeminiAgentDrafter:
    """
    Google GenAI SDK Drafter (Google Agent Framework).
    Boundary: LLM proposes wording only; deterministic code owns the authoritative business figures.
    """
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
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
    ) -> str:
        if action_type == ActionType.NUDGE:
            return f"Hello, this is a reminder regarding expense report {report_id} submitted by {submitter} for {currency} {amount} ({description}). Please review and sign off when convenient."
        else:
            return f"Hello, this is an automated escalation for expense report {report_id} from {submitter} for {currency} {amount} ({description}). The primary approver has not responded."

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
        # Injected mock takes priority for deterministic test scenarios
        if injected_mock_response:
            return injected_mock_response

        fallback = self._deterministic_fallback(action_type, report_id, submitter, amount, currency, description)

        if not self.client:
            return fallback

        prompt = build_drafting_prompt(
            action_type, report_id, submitter, amount, currency, description, hours_pending
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            raw_text = response.text.strip()
            
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
                return proposal.message.strip()
            except Exception as parse_err:
                logger.warning(
                    "Structured output validation failed (%s). Malformed JSON/schema rejected; using deterministic fallback.",
                    str(parse_err)
                )
                return fallback

        except Exception as e:
            logger.warning("Gemini generation failed (%s), using resilient fallback template", str(e))
            return fallback
