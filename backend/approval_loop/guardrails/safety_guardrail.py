import os
import re
import base64
import binascii
import logging
import unicodedata
from typing import Iterator, Optional, Any
from pydantic import BaseModel, Field, ConfigDict

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
    model_config = ConfigDict(protected_namespaces=())

    passed: bool = True
    reason: str = "Input and output conform to model safety boundaries."
    detected_threats: list[str] = Field(default_factory=list)
    guardrail_layer: str = "Google Cloud Model Armor & Deterministic Safety Guardrail"
    model_armor_sanitized: bool = False

class ModelSafetyGuardrail:
    """
    Model Safety & Prompt Defense Layer (Google Cloud Model Armor Integration):
    Inline security layer integrating Google Cloud Model Armor (google-cloud-modelarmor SDK)
    to sanitize user prompts and model responses before/after Gemini inference and before Agent Gateway evaluation.
    
    CRITICAL ARCHITECTURAL BOUNDARIES:
    Agent -> Model Armor (Pre-LLM) -> Gemini -> Model Armor (Post-LLM) -> Agent Gateway -> Policy Engine -> Async Runtime -> Enterprise Action
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

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        template_id: Optional[str] = None,
        fail_closed: Optional[bool] = None,
        enabled: Optional[bool] = None,
        model_armor_client: Optional[Any] = None
    ):
        from approval_loop.config import Settings
        settings = Settings()

        self.project_id = project_id or settings.google_cloud_project
        self.location = location or settings.model_armor_location
        self.template_id = template_id or settings.model_armor_template_id
        self.fail_closed = fail_closed if fail_closed is not None else settings.model_armor_fail_closed
        self.enabled = enabled if enabled is not None else settings.model_armor_enabled

        self._compiled_injections = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        self._compiled_secrets = [re.compile(p, re.IGNORECASE) for p in self.SECRET_LEAKAGE_PATTERNS]

        self.template_resource_name = f"projects/{self.project_id}/locations/{self.location}/templates/{self.template_id}"
        self.model_armor_client = model_armor_client

        if self.enabled and self.model_armor_client is None and not self.project_id:
            logger.warning("Model Armor skipped: GOOGLE_CLOUD_PROJECT is not set; only the pattern filter runs.")
        elif self.enabled and self.model_armor_client is None:
            # Check for local Application Default Credentials or Cloud Run environment
            adc_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            standard_gcp_path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
            win_gcp_path = os.path.join(os.getenv("APPDATA", ""), "gcloud", "application_default_credentials.json") if os.getenv("APPDATA") else ""
            has_local_adc = bool(
                (adc_path and os.path.exists(adc_path)) or
                os.path.exists(standard_gcp_path) or
                (win_gcp_path and os.path.exists(win_gcp_path)) or
                os.getenv("K_SERVICE")  # Google Cloud Run
            )
            if has_local_adc:
                try:
                    import google.auth
                    from google.auth.exceptions import DefaultCredentialsError
                    try:
                        credentials, _ = google.auth.default()
                    except (DefaultCredentialsError, Exception):
                        credentials = None

                    if credentials:
                        from google.cloud import modelarmor_v1
                        from google.api_core.client_options import ClientOptions
                        client_opts = ClientOptions(api_endpoint=f"modelarmor.{self.location}.rep.googleapis.com")
                        self.model_armor_client = modelarmor_v1.ModelArmorClient(credentials=credentials, client_options=client_opts)
                    else:
                        self.model_armor_client = None
                except Exception as e:
                    logger.warning("Could not initialize Google Cloud ModelArmorClient: %s", str(e))
                    self.model_armor_client = None
            else:
                self.model_armor_client = None

    def _is_threat_match(self, match_state: Any) -> bool:
        if not match_state:
            return False
        state_str = str(match_state)
        if "NO_MATCH_FOUND" in state_str:
            return False
        return "MATCH_FOUND" in state_str or state_str == "MATCH_FOUND" or getattr(match_state, "name", "") == "MATCH_FOUND"

    def _extract_threats_from_response(self, res_data: Any) -> list[str]:
        threats = []
        if not res_data:
            return threats

        match_state = getattr(res_data, "filter_match_state", None)
        if self._is_threat_match(match_state):
            threats.append("Model Armor filter match found")

        # Check sub-results if available
        filter_results = getattr(res_data, "filter_results", {})
        if isinstance(filter_results, dict):
            for f_name, f_val in filter_results.items():
                threats.append(f"Model Armor filter '{f_name}': match")
        elif isinstance(filter_results, list):
            for f_val in filter_results:
                threats.append(f"Model Armor filter match: {getattr(f_val, 'name', 'detected')}")

        for sub_attr in [
            "pi_and_jailbreak_filter_result",
            "sdp_filter_result",
            "rai_filter_result",
            "malicious_uri_filter_result",
            "virus_scan_filter_result",
            "csam_filter_result"
        ]:
            sub_res = getattr(res_data, sub_attr, None)
            if sub_res:
                match_val = getattr(sub_res, "filter_match_state", None)
                if self._is_threat_match(match_val):
                    threats.append(f"Model Armor threat detected in {sub_attr}")

        if not threats:
            threats.append("Google Cloud Model Armor safety filter policy violation")
        return threats

    def _injection_hits(self, text: str) -> list[str]:
        variants = list(dict.fromkeys(_variants(text)))
        return [p.pattern for p in self._compiled_injections if any(p.search(v) for v in variants)]

    def _secret_hit(self, text: str) -> bool:
        # Secrets are matched on the original and Unicode-normalised text only (digit swaps would corrupt key formats).
        candidates = (text, _normalized(text))
        return any(p.search(c) for p in self._compiled_secrets for c in candidates)

    def inspect_prompt(self, prompt_text: str) -> ModelSafetyResult:
        """Inspects incoming user/system prompts using Google Cloud Model Armor API pre-LLM inference."""
        if not prompt_text:
            return ModelSafetyResult(passed=True)

        model_armor_threats = []
        model_armor_called = False

        # 1. Call Google Cloud Model Armor API (Pre-LLM)
        if self.enabled and self.model_armor_client:
            model_armor_called = True
            try:
                from google.cloud import modelarmor_v1
                req = modelarmor_v1.SanitizeUserPromptRequest(
                    name=self.template_resource_name,
                    user_prompt_data=modelarmor_v1.DataItem(text=prompt_text)
                )
                resp = self.model_armor_client.sanitize_user_prompt(request=req)
                res_data = getattr(resp, "sanitization_result", None)
                if res_data:
                    match_state = getattr(res_data, "filter_match_state", None)
                    if self._is_threat_match(match_state):
                        model_armor_threats = self._extract_threats_from_response(res_data)
                        logger.warning("Google Cloud Model Armor blocked prompt: %s", model_armor_threats)
                        return ModelSafetyResult(
                            passed=False,
                            reason=f"Google Cloud Model Armor Intercept: {'; '.join(model_armor_threats)}",
                            detected_threats=model_armor_threats,
                            guardrail_layer="Google Cloud Model Armor",
                            model_armor_sanitized=True
                        )
            except Exception as e:
                logger.warning("Google Cloud Model Armor API sanitize_user_prompt failed: %s", str(e))
                if self.fail_closed:
                    return ModelSafetyResult(
                        passed=False,
                        reason=f"Google Cloud Model Armor Intercept: Security service unavailable/error (fail-closed rule enforced). Error: {str(e)}",
                        detected_threats=["model_armor_service_unavailable"],
                        guardrail_layer="Google Cloud Model Armor (Fail-Closed Enforcement)",
                        model_armor_sanitized=False
                    )

        # 2. Baseline Deterministic Defense Layer
        threats = [f"Prompt injection pattern detected: '{p}'" for p in self._injection_hits(prompt_text)]
        if self._secret_hit(prompt_text):
            threats.append("Potential secret/credential detected in prompt text")

        if threats:
            logger.warning("Model safety guardrail intercepted prompt threats: %s", threats)
            return ModelSafetyResult(
                passed=False,
                reason=f"Deterministic Model Safety Guardrail Intercept: {'; '.join(threats)}",
                detected_threats=threats,
                guardrail_layer="Deterministic Model Safety Guardrail",
                model_armor_sanitized=model_armor_called
            )

        return ModelSafetyResult(
            passed=True,
            reason="Prompt verified safe by Google Cloud Model Armor and Deterministic Safety Guardrail.",
            model_armor_sanitized=model_armor_called
        )

    def inspect_model_output(self, output_text: str, user_prompt: Optional[str] = None) -> ModelSafetyResult:
        """Inspects LLM-generated output using Google Cloud Model Armor API post-LLM inference."""
        if not output_text:
            return ModelSafetyResult(passed=True)

        model_armor_threats = []
        model_armor_called = False

        # 1. Call Google Cloud Model Armor API (Post-LLM)
        if self.enabled and self.model_armor_client:
            model_armor_called = True
            try:
                from google.cloud import modelarmor_v1
                req = modelarmor_v1.SanitizeModelResponseRequest(
                    name=self.template_resource_name,
                    model_response_data=modelarmor_v1.DataItem(text=output_text),
                    user_prompt=user_prompt or ""
                )
                resp = self.model_armor_client.sanitize_model_response(request=req)
                res_data = getattr(resp, "sanitization_result", None)
                if res_data:
                    match_state = getattr(res_data, "filter_match_state", None)
                    if self._is_threat_match(match_state):
                        model_armor_threats = self._extract_threats_from_response(res_data)
                        logger.warning("Google Cloud Model Armor blocked model response: %s", model_armor_threats)
                        return ModelSafetyResult(
                            passed=False,
                            reason=f"Google Cloud Model Armor Intercept: {'; '.join(model_armor_threats)}",
                            detected_threats=model_armor_threats,
                            guardrail_layer="Google Cloud Model Armor",
                            model_armor_sanitized=True
                        )
            except Exception as e:
                logger.warning("Google Cloud Model Armor API sanitize_model_response failed: %s", str(e))
                if self.fail_closed:
                    return ModelSafetyResult(
                        passed=False,
                        reason=f"Google Cloud Model Armor Intercept: Security service unavailable/error (fail-closed rule enforced). Error: {str(e)}",
                        detected_threats=["model_armor_service_unavailable"],
                        guardrail_layer="Google Cloud Model Armor (Fail-Closed Enforcement)",
                        model_armor_sanitized=False
                    )

        # 2. Baseline Deterministic Defense Layer
        threats = [f"Unsafe executable/injection pattern in output: '{p}'" for p in self._injection_hits(output_text)]
        if self._secret_hit(output_text):
            threats.append("Credential leak prevented: Output contained sensitive key pattern.")

        if threats:
            logger.warning("Model safety guardrail intercepted output threats: %s", threats)
            return ModelSafetyResult(
                passed=False,
                reason=f"Deterministic Model Safety Guardrail Intercept: {'; '.join(threats)}",
                detected_threats=threats,
                guardrail_layer="Deterministic Model Safety Guardrail",
                model_armor_sanitized=model_armor_called
            )

        return ModelSafetyResult(
            passed=True,
            reason="Model output verified safe by Google Cloud Model Armor and Deterministic Safety Guardrail.",
            model_armor_sanitized=model_armor_called
        )
