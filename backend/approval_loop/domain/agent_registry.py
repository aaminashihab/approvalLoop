from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class AgentStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AgentRegistration(BaseModel):
    """
    Formal Agent Registry Schema:
    Answers:
    1. Which agent is this?
    2. Which version is running?
    3. What actions is this agent allowed to request?
    4. Which policy profile applies?
    5. Which tools can it access?
    """
    agent_id: str
    name: str
    description: str
    owner: str
    version: str = "1.0.0"
    status: AgentStatus = AgentStatus.ACTIVE
    capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    policy_profile: str = "finance-v3"
    risk_level: RiskLevel = RiskLevel.MEDIUM
    api_key_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "version": self.version,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "allowed_tools": self.allowed_tools,
            "allowed_actions": self.allowed_actions,
            "policy_profile": self.policy_profile,
            "risk_level": self.risk_level.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

class AgentRegistryService:
    """
    Registry management service providing CRUD and authorization lookups for the Agent Fleet.
    """
    def __init__(self, repo: Any = None):
        self.repo = repo
        self._in_memory_agents: dict[str, AgentRegistration] = {}
        self._init_default_fleet()

    def _init_default_fleet(self):
        default_agents = [
            AgentRegistration(
                agent_id="finance-agent",
                name="Institutional Finance Agent",
                description="Autonomous financial operations agent proposing refunds, expense adjustments, and invoice approvals.",
                owner="finance-ops@company.internal",
                version="1.2.0",
                status=AgentStatus.ACTIVE,
                capabilities=["financial_reasoning", "expense_analysis", "refund_assessment"],
                allowed_tools=["payment_gateway", "erp_ledger", "notification_worker"],
                allowed_actions=["issue_refund", "approve_expense", "escalate_stalled_approval"],
                policy_profile="finance-v3",
                risk_level=RiskLevel.HIGH
            ),
            AgentRegistration(
                agent_id="support-agent",
                name="Tier-2 Support Operations Agent",
                description="Autonomous customer support agent evaluating SLA disputes, escalations, and account credits.",
                owner="support-ops@company.internal",
                version="1.1.0",
                status=AgentStatus.ACTIVE,
                capabilities=["ticket_triage", "sla_evaluation", "credit_calculation"],
                allowed_tools=["zendesk_api", "billing_system", "notification_worker"],
                allowed_actions=["credit_account", "escalate_ticket", "sla_override"],
                policy_profile="support-v1",
                risk_level=RiskLevel.MEDIUM
            ),
            AgentRegistration(
                agent_id="sales-agent",
                name="Enterprise Sales Deal Desk Agent",
                description="Autonomous commercial deal desk agent proposing contract discounts, fee waivers, and terms.",
                owner="deal-desk@company.internal",
                version="1.0.0",
                status=AgentStatus.ACTIVE,
                capabilities=["deal_structuring", "discount_governance", "contract_review"],
                allowed_tools=["crm_salesforce", "contract_vault", "notification_worker"],
                allowed_actions=["grant_discount", "waive_fee", "custom_contract_terms"],
                policy_profile="sales-v1",
                risk_level=RiskLevel.HIGH
            ),
        ]
        for a in default_agents:
            self.register_agent(a)

    def register_agent(self, agent: AgentRegistration) -> AgentRegistration:
        agent.updated_at = utc_now()
        if self.repo and hasattr(self.repo, "save_agent_registration"):
            self.repo.save_agent_registration(agent)
        else:
            self._in_memory_agents[agent.agent_id] = agent
        return agent

    def get_agent(self, agent_id: str) -> Optional[AgentRegistration]:
        if self.repo and hasattr(self.repo, "get_agent_registration"):
            return self.repo.get_agent_registration(agent_id)
        return self._in_memory_agents.get(agent_id)

    def list_agents(self) -> list[AgentRegistration]:
        if self.repo and hasattr(self.repo, "list_agent_registrations"):
            return self.repo.list_agent_registrations()
        return list(self._in_memory_agents.values())

    def update_agent_status(self, agent_id: str, status: AgentStatus) -> Optional[AgentRegistration]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None
        agent.status = status
        agent.updated_at = utc_now()
        return self.register_agent(agent)

    def is_action_allowed(self, agent_id: str, action_name: str) -> bool:
        agent = self.get_agent(agent_id)
        if not agent or agent.status != AgentStatus.ACTIVE:
            return False
        return action_name in agent.allowed_actions

    def is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        agent = self.get_agent(agent_id)
        if not agent or agent.status != AgentStatus.ACTIVE:
            return False
        return tool_name in agent.allowed_tools
