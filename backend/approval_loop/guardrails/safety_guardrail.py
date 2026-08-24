import re
import logging
from typing import Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger("approval_loop.guardrails")

class ModelSafetyResult(BaseModel):
    passed: bool = True
    reason: str = "Input and output conform to model safety boundaries."
    detected_threats: list[str] = Field(default_factory=list)
    guardrail_layer: str = "Deterministic model-safety guardrail"

class ModelSafetyGuardrail:
    """
    Model Safety & Prompt Defense Layer:
    Deterministic Model-Safety Guardrail providing defense against prompt injections,
    adversarial overrides, secret leakage, and malicious script injections BEFORE and AFTER LLM inference.
    
    CRITICAL ARCHITECTURAL BOUNDARY:
    1. Deterministic Model-Safety Guardrail (filters malicious inputs and adversarial text)
    2. Deterministic Action Validation (4-point parameter matching, decimal types, ID checks)
    3. Corporate Authorization Policy (financial limits, domain whitelist, environment policy)
    4. Execution Governance (ApprovalLoop Agent Gateway)
    
    In all cases: Model output CANNOT directly authorize execution.
    """
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions",
        r"system\s*override",
        r"bypass\s+(safety|security|policy|validator|auth|guardrail)",
        r"you\s+are\s+now\s+in\s+(dan|developer|root|unrestricted)\s+mode",
        r"forget\s+all\s+(rules|constraints|directives)",
        r"disregard\s+(above|previous|system)\s+(prompt|rules)",
        r"act\s+as\s+an?\s+unrestricted",
        r"<script.*?>",
        r"javascript:",
        r"onload\s*=",
        r"onerror\s*=",
        r"eval\(",
        r"exec\(",
        r"system\(",
        r"subprocess\.",
        r"drop\s+(table|database|schema)",
        r"union\s+select",
        r"base64_decode",
        r"rm\s+-rf",
        r"curl\s+.*\|\s*sh",
        r"wget\s+.*\|\s*bash",
        r"cat\s+/etc/passwd",
        r"cat\s+/etc/shadow",
    ]

    SECRET_LEAKAGE_PATTERNS = [
        r"AIza[0-9A-Za-z-_]{35}",           # Google API key pattern
        r"ghp_[0-9a-zA-Z]{36}",            # GitHub personal token
        r"gho_[0-9a-zA-Z]{36}",            # GitHub OAuth token
        r"xox[baprs]-[0-9a-zA-Z-]{10,48}", # Slack token
        r"AKIA[0-9A-Z]{16}",               # AWS Access Key ID
        r"-----BEGIN [A-Z\s]*KEY-----",    # Private Keys
        r"sk-proj-[0-9a-zA-Z-_]{20,}",     # OpenAI API Key pattern
        r"sk-ant-api[0-9a-zA-Z-_]{20,}",   # Anthropic API key
    ]

    def __init__(self):
        self._compiled_injections = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        self._compiled_secrets = [re.compile(p, re.IGNORECASE) for p in self.SECRET_LEAKAGE_PATTERNS]

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
                reason=f"Deterministic Model Safety Guardrail Intercept: {'; '.join(threats)}",
                detected_threats=threats
            )

        return ModelSafetyResult(passed=True, reason="Prompt verified safe by Deterministic Model Safety Guardrail.")

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
                reason=f"Deterministic Model Safety Guardrail Intercept: {'; '.join(threats)}",
                detected_threats=threats
            )

        return ModelSafetyResult(passed=True, reason="Model output verified safe by Deterministic Model Safety Guardrail.")
