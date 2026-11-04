import re
import base64
import binascii
import logging
import unicodedata
from typing import Iterator, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger("approval_loop.guardrails")

# Invisible characters commonly used to split trigger words (e.g. a zero-width space inside "ignore").
_INVISIBLE = dict.fromkeys([0x00AD, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF], None)
# Cyrillic/Greek letters that render like Latin ones (a deliberately small, high-confidence set).
_CONFUSABLES = {
    0x0430: "a", 0x0435: "e", 0x043E: "o", 0x0440: "p", 0x0441: "c", 0x0443: "y", 0x0445: "x",
    0x0456: "i", 0x0458: "j", 0x0455: "s", 0x0410: "A", 0x0415: "E", 0x041E: "O", 0x0420: "P",
    0x0421: "C", 0x0425: "X", 0x0406: "I", 0x0422: "T", 0x041D: "H", 0x041A: "K", 0x041C: "M",
    0x0412: "B", 0x03BF: "o", 0x03B1: "a", 0x03B9: "i", 0x03B5: "e", 0x039F: "O", 0x0399: "I",
}
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i", "|": "i"})
# Single letters separated by single separators: "i-g-n-o-r-e", "i g n o r e", "i.g.n.o.r.e".
_SPACED = re.compile(r"\b(?:\w[\s\-_.*]){2,}\w\b")
_B64_TOKEN = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(_INVISIBLE).translate(_CONFUSABLES)


def _variants(text: str) -> Iterator[str]:
    """
    The original text plus de-obfuscated forms. Patterns are matched against each, so a known
    attack phrase is still caught when disguised. Paraphrases are NOT caught by any regex; that
    needs a semantic classifier, and the policy tiers (not this filter) are the security boundary.
    """
    yield text
    norm = _normalized(text)
    collapsed = _SPACED.sub(lambda m: re.sub(r"[\s\-_.*]", "", m.group(0)), norm)
    for v in (norm, collapsed, norm.translate(_LEET), collapsed.translate(_LEET)):
        yield v
    for token in _B64_TOKEN.findall(norm):
        try:
            decoded = base64.b64decode(token + "=" * (-len(token) % 4), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if decoded.isprintable():
            yield decoded

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

    def _injection_hits(self, text: str) -> list[str]:
        variants = list(dict.fromkeys(_variants(text)))
        return [p.pattern for p in self._compiled_injections if any(p.search(v) for v in variants)]

    def _secret_hit(self, text: str) -> bool:
        # Secrets are matched on the original and Unicode-normalised text only (digit swaps would corrupt key formats).
        candidates = (text, _normalized(text))
        return any(p.search(c) for p in self._compiled_secrets for c in candidates)

    def inspect_prompt(self, prompt_text: str) -> ModelSafetyResult:
        """Inspects incoming user/system prompts for adversarial injection attempts."""
        if not prompt_text:
            return ModelSafetyResult(passed=True)

        threats = [f"Prompt injection pattern detected: '{p}'" for p in self._injection_hits(prompt_text)]
        if self._secret_hit(prompt_text):
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

        threats = [f"Unsafe executable/injection pattern in output: '{p}'" for p in self._injection_hits(output_text)]
        if self._secret_hit(output_text):
            threats.append("Credential leak prevented: Output contained sensitive key pattern.")

        if threats:
            logger.warning("Model safety guardrail intercepted output threats: %s", threats)
            return ModelSafetyResult(
                passed=False,
                reason=f"Model Armor Intercept: {'; '.join(threats)}",
                detected_threats=threats
            )

        return ModelSafetyResult(passed=True, reason="Model output verified safe by Model Armor.")
