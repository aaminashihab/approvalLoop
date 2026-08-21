import re
import logging
from typing import Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger("approval_loop.guardrails")

class ModelSafetyResult(BaseModel):
    passed: bool = True
    reason: str = "Input and output conform to model safety boundaries."
    detected_threats: list[str] = Field(default_factory=list)
    guardrail_layer: str = "Model Armor / Safety Filter"

class ModelSafetyGuardrail:
    """
    Model Safety & Prompt Defense Layer (Model Armor Concept):
    
    Provides defense against prompt injections, adversarial overrides, secret leakage,
    and malicious script injections BEFORE and AFTER LLM inference.
    
    CRITICAL ARCHITECTURAL BOUNDARY:
    1. Model Safety / Prompt Defense (This layer: filters malicious inputs and adversarial text)
    2. Deterministic Action Validation (4-point parameter matching, decimal types, ID checks)
    3. Corporate Authorization Policy (financial limits, domain whitelist, environment policy)
    4. Execution Governance (ApprovalLoop Agent Gateway)
    
    In all cases: Model output CANNOT directly authorize execution.
    """
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
        r"system\s*override",
        r"bypass\s+(safety|security|policy|validator)",
        r"you\s+are\s+now\s+in\s+dan\s+mode",
        r"forget\s+all\s+rules",
        r"<script.*?>",
        r"javascript:",
        r"eval\(",
        r"drop\s+table",
        r"union\s+select",
        r"base64_decode",
    ]

    SECRET_LEAKAGE_PATTERNS = [
        r"AIza[0-9A-Za-z-_]{35}",           # Google API key pattern
        r"ghp_[0-9a-zA-Z]{36}",            # GitHub personal token
        r"xox[baprs]-[0-9a-zA-Z-]{10,48}", # Slack token
    ]

    def __init__(self):
        self._compiled_injections = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        self._compiled_secrets = [re.compile(p) for p in self.SECRET_LEAKAGE_PATTERNS]

    def inspect_prompt(self, prompt_text: str) -> ModelSafetyResult:
        """Inspects incoming user/system prompts for adversarial injection attempts."""
        if not prompt_text:
            return ModelSafetyResult(passed=True)

        threats = []
        for pattern in self._compiled_injections:
            if pattern.search(prompt_text):
                threats.append(f"Prompt injection pattern detected: '{pattern.pattern}'")

        for pattern in self._compiled_secrets:
            if pattern.search(prompt_text):
                threats.append("Potential secret/credential detected in prompt text")

        if threats:
            logger.warning("Model safety guardrail intercepted prompt threats: %s", threats)
            return ModelSafetyResult(
                passed=False,
                reason=f"Model Armor Intercept: {'; '.join(threats)}",
                detected_threats=threats
            )

        return ModelSafetyResult(passed=True, reason="Prompt verified safe by Model Armor.")

    def inspect_model_output(self, output_text: str) -> ModelSafetyResult:
        """Inspects LLM-generated output for unsafe payloads or leaked credentials."""
        if not output_text:
            return ModelSafetyResult(passed=True)

        threats = []
        for pattern in self._compiled_injections:
            if pattern.search(output_text):
                threats.append(f"Unsafe executable/injection pattern in output: '{pattern.pattern}'")

        for pattern in self._compiled_secrets:
            if pattern.search(output_text):
                threats.append("Credential leak prevented: Output contained sensitive key pattern.")

        if threats:
            logger.warning("Model safety guardrail intercepted output threats: %s", threats)
            return ModelSafetyResult(
                passed=False,
                reason=f"Model Armor Intercept: {'; '.join(threats)}",
                detected_threats=threats
            )

        return ModelSafetyResult(passed=True, reason="Model output verified safe by Model Armor.")
