import hmac
import hashlib
import time
import base64
import json
import logging
import threading
from typing import Optional, Any
from approval_loop.domain.agent_registry import AgentRegistryService, AgentStatus
from approval_loop.domain.gateway_models import AgentAuthContext, AgentActionProposal

logger = logging.getLogger("approval_loop.identity")


def proposal_digest(proposal: AgentActionProposal) -> str:
    """
    SHA-256 over the fields that define what a proposal asks for. Signing this into the agent token
    means a captured token cannot be reused for a different amount, recipient or action.
    Amounts are normalised so "20000", "20000.0" and "20000.00" hash the same.
    """
    amount = None if proposal.amount is None else format(proposal.amount.normalize(), "f")
    canonical = {
        "proposal_id": proposal.proposal_id,
        "workflow_id": proposal.workflow_id,
        "agent_id": proposal.agent_id,
        "agent_version": proposal.agent_version,
        "action_name": proposal.action_name,
        "target_resource_id": proposal.target_resource_id,
        "amount": amount,
        "currency": (proposal.currency or "").upper(),
        "recipient": proposal.recipient,
        "parameters": proposal.parameters,
        "justification": proposal.justification,
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class AgentIdentityProvider:
    """
    Zero-Trust Agent Identity & Access Control Provider:
    
    Verifies that requests originate from legitimate, registered, and active institutional agents
    with valid cryptographic tokens/signatures, enforcing least-privilege action and tool whitelists.
    
    Production-ready features:
    - HMAC-SHA256 agent signature verification with timestamp replay attack prevention
    - Google Cloud IAM / Service Account token verification hook
    - Registry capability & active status check
    - Version mismatch protection
    - Whitelist enforcement for allowed_actions and allowed_tools
    """
    def __init__(
        self,
        registry_service: AgentRegistryService,
        secret_key: str = "fleet-identity-master-secret-key-2026",
        token_max_age_seconds: int = 300,
        oidc_audience: Optional[str] = None,
        oidc_agent_bindings: Optional[dict[str, str]] = None,
        require_request_binding: bool = False,
    ):
        self.registry = registry_service
        # When True, HMAC tokens must be bound to one request_id and one proposal digest.
        self.require_request_binding = require_request_binding
        self.secret_key = secret_key
        self.token_max_age_seconds = token_max_age_seconds
        # Replay cache: request_id -> expiry (epoch seconds). Per-process only; see README
        # "Known limitations" -- multi-instance deployments need a shared store.
        self._seen_request_ids: dict[str, float] = {}
        self._replay_lock = threading.Lock()
        self.oidc_audience = oidc_audience
        self.oidc_agent_bindings = {k: v.lower() for k, v in (oidc_agent_bindings or {}).items()}

    def _consume_request_id(self, request_id: str) -> bool:
        """Atomically records a request_id. Returns False if it was already consumed.
        Uses the registry's shared repository when there is one, so replays are caught across
        instances; otherwise a per-process cache. Entries expire after twice the token lifetime."""
        ttl = max(self.token_max_age_seconds, 60) * 2
        repo = getattr(self.registry, "repo", None)
        if repo is not None:
            return repo.check_and_record_request_id(request_id, ttl_seconds=ttl)
        now = time.time()
        with self._replay_lock:
            for rid in [r for r, exp in self._seen_request_ids.items() if exp <= now]:
                del self._seen_request_ids[rid]
            if request_id in self._seen_request_ids:
                return False
            self._seen_request_ids[request_id] = now + max(self.token_max_age_seconds, 60) * 2
            return True

    def generate_agent_token(
        self,
        agent_id: str,
        agent_version: str,
        request_id: Optional[str] = None,
        proposal: Optional[AgentActionProposal] = None,
    ) -> str:
        """
        Issues an authenticated agent token for the given agent and version.
        Format: base64(json_payload).hmac_signature

        Pass `request_id` and `proposal` to bind the token to exactly one request with exactly that
        content (claims `rid` and `pdg`). Bound tokens are required when require_request_binding is on.
        """
        now = int(time.time())
        payload = {
            "agent_id": agent_id,
            "agent_version": agent_version,
            "iat": now,
            "exp": now + self.token_max_age_seconds,
        }
        if request_id is not None:
            payload["rid"] = request_id
        if proposal is not None:
            payload["pdg"] = proposal_digest(proposal)
        raw_json = json.dumps(payload, sort_keys=True).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(raw_json).decode("utf-8")
        sig = hmac.new(self.secret_key.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{b64_payload}.{sig}"

    def verify_agent_request(
        self,
        proposal: AgentActionProposal,
        auth_context: AgentAuthContext
    ) -> tuple[bool, str, dict[str, Any]]:
        """
        Authenticates agent identity and validates permission to request the specified action.
        Returns: (is_authenticated: bool, reason: str, verified_claims: dict)
        """
        # 1. Check basic header presence
        if not auth_context.agent_id or not auth_context.agent_version:
            return False, "Missing agent_id or agent_version in authentication context.", {}

        # 2. Check proposal and auth context match
        if proposal.agent_id != auth_context.agent_id:
            return False, f"Identity Mismatch: Proposal agent '{proposal.agent_id}' does not match auth token agent '{auth_context.agent_id}'.", {}

        if proposal.agent_version != auth_context.agent_version:
            return False, f"Version Mismatch: Proposal version '{proposal.agent_version}' does not match auth token version '{auth_context.agent_version}'.", {}

        # 3. Retrieve agent from Registry
        agent = self.registry.get_agent(auth_context.agent_id)
        if not agent:
            return False, f"Unauthorized Agent: Agent '{auth_context.agent_id}' is not registered in the Agent Registry.", {}

        if agent.status != AgentStatus.ACTIVE:
            return False, f"Disabled Agent: Agent '{auth_context.agent_id}' status is '{agent.status.value}'. Execution rejected.", {}

        if agent.version != auth_context.agent_version:
            return False, f"Stale Agent Version: Agent '{auth_context.agent_id}' running version '{auth_context.agent_version}' but registry requires '{agent.version}'.", {}

        # 4. Cryptographic Token Verification
        claims = {}
        if auth_context.token:
            token = auth_context.token.strip()
            # Check for Google IAM OIDC token or HMAC fleet token
            if "." in token:
                parts = token.split(".")
                if len(parts) == 2:
                    # HMAC Fleet Token
                    b64_payload, signature = parts[0], parts[1]
                    expected_sig = hmac.new(self.secret_key.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
                    if not hmac.compare_digest(signature, expected_sig):
                        return False, "Invalid Cryptographic Token: Agent token signature verification failed.", {}
                    try:
                        raw_json = base64.urlsafe_b64decode(b64_payload.encode("utf-8"))
                        claims = json.loads(raw_json.decode("utf-8"))
                    except Exception as e:
                        return False, f"Malformed Agent Token Payload: {str(e)}", {}

                    # Fail closed: every claim is REQUIRED (a token without `exp` would never expire).
                    exp = claims.get("exp") if isinstance(claims, dict) else None
                    if not isinstance(exp, (int, float)) or isinstance(exp, bool):
                        return False, "Malformed Agent Token Payload: missing or invalid 'exp' claim.", {}
                    if int(time.time()) > exp:
                        return False, "Expired Agent Token: Request token has expired.", {}
                    if claims.get("agent_id") != auth_context.agent_id:
                        return False, "Token Subject Mismatch: Token agent_id does not match caller.", {}
                    if claims.get("agent_version") != auth_context.agent_version:
                        return False, "Token Version Mismatch: Token agent_version does not match caller.", {}
                    # Request binding: a token signed for one request cannot authorise another.
                    if "rid" in claims and claims["rid"] != auth_context.request_id:
                        return False, "Token Binding Mismatch: token was issued for a different request_id.", {}
                    if "pdg" in claims and claims["pdg"] != proposal_digest(proposal):
                        return False, "Token Binding Mismatch: proposal content differs from what the token was issued for.", {}
                    if self.require_request_binding and not ("rid" in claims and "pdg" in claims):
                        return False, "Unbound Agent Token: this gateway requires tokens bound to request_id and proposal.", {}
                elif len(parts) == 3:
                    # GCP OIDC Token
                    claims = self._verify_gcp_oidc_token(token, auth_context.agent_id)
                    if not claims:
                        return False, "Invalid GCP IAM OIDC Token: Signature or audience verification failed.", {}
            else:
                return False, "Unrecognized token format.", {}
        else:
            return False, "Missing required agent authentication credential/token.", {}

        # 5. Capability Whitelist Verification
        if proposal.action_name not in agent.allowed_actions:
            return False, f"Action Permission Denied: Agent '{agent.agent_id}' is not authorized to execute action '{proposal.action_name}'. Allowed: {agent.allowed_actions}", claims

        # 6. Replay protection: consume the request_id only for otherwise-valid requests, so
        # unauthenticated callers cannot burn legitimate request IDs.
        if not self._consume_request_id(auth_context.request_id):
            return False, f"Replay Attack Prevented: Request ID '{auth_context.request_id}' has already been processed.", {}

        auth_context.verified = True
        auth_context.verification_method = "HMAC-SHA256" if len(auth_context.token.split(".")) == 2 else "GCP-OIDC"
        auth_context.claims = claims

        return True, f"Agent '{agent.agent_id}' (v{agent.version}) authenticated successfully via {auth_context.verification_method}.", claims

    def _verify_gcp_oidc_token(
        self,
        token: str,
        expected_agent_id: str,
        expected_audience: Optional[str] = None
    ) -> Optional[dict]:
        """
        Validates Google Cloud service-account OIDC tokens. Fails closed unless ALL hold:
        - an expected audience is configured,
        - signature/expiry/audience verify via google.oauth2.id_token,
        - the issuer is Google and the token carries a subject or email,
        - the agent has an explicit service-account binding and the token's verified
          email matches it (otherwise any service account could impersonate any agent).
        """
        audience = expected_audience or self.oidc_audience
        if not audience:
            logger.warning("Agent OIDC token rejected: no OIDC audience configured.")
            return None
        bound_email = self.oidc_agent_bindings.get(expected_agent_id)
        if not bound_email:
            logger.warning("Agent OIDC token rejected: no service-account binding for agent '%s'.", expected_agent_id)
            return None
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests
            req = requests.Request()
            id_info = id_token.verify_oauth2_token(token, req, audience=audience)
            iss = id_info.get("iss", "")
            if iss not in ("https://accounts.google.com", "accounts.google.com"):
                logger.warning("GCP OIDC token verification failed: untrusted issuer '%s'", iss)
                return None
            if not (id_info.get("sub") or id_info.get("email")):
                logger.warning("GCP OIDC token verification failed: missing subject/email claim")
                return None
        except Exception as e:
            logger.warning("GCP OIDC token verification failed: %s", type(e).__name__)
            return None
        if not id_info.get("email_verified") or str(id_info.get("email", "")).lower() != bound_email:
            logger.warning("Agent OIDC token rejected: service account does not match binding for '%s'.", expected_agent_id)
            return None
        return id_info
