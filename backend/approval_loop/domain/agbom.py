from typing import Any, Optional
from pydantic import BaseModel, Field
from approval_loop.config import Settings

class AgentBillOfMaterials(BaseModel):
    """
    Declared Runtime Dependency, Fleet Inventory, and Safety Manifest (AgBOM):
    Standardized declaration of institutional agent fleet, models, datastores, safety gates, and runtime dependencies.
    """
    agent_name: str = "ApprovalLoop"
    edition: str = "Fortified Enterprise Fleet"
    version: str = "2.1.0"
    track: str = "Taskmaster"
    environment: str = "demo"
    model: str = "gemini-3.5-flash"
    framework: str = "Google GenAI SDK (google-genai)"
    runtime: str = "Google Cloud Run"
    project_id: str = "approval-loop-hackathon"
    trigger: str = "Google Cloud Scheduler (* * * * *)"
    data_sources: list[str] = Field(default_factory=lambda: ["expense_reports", "approver_registry", "agent_registry", "workflow_memories"])
    state_store: str = "Google Cloud Firestore"
    tools: list[str] = Field(default_factory=lambda: ["notification_worker", "firestore_transaction_outbox", "payment_gateway", "erp_ledger_sync"])
    safety_mechanisms: list[str] = Field(default_factory=lambda: [
        "zero_trust_cryptographic_agent_identity",
        "deterministic_model_safety_guardrail",
        "approval_loop_agent_gateway",
        "deterministic_state_machine",
        "4_point_safety_validator",
        "corporate_policy_engine",
        "transactional_outbox_claiming",
        "human_in_the_loop_approval_queue",
        "persistent_cross_session_memory_bank",
        "leased_async_execution_with_crash_recovery",
        "scenario_13_conditional_transition_guard",
        "decimal_financial_precision",
        "opentelemetry_distributed_tracing"
    ])
    skills: list[str] = Field(default_factory=lambda: ["approval_escalation", "financial_refund_governance", "deal_desk_discount_authorization"])
    agent_fleet: list[str] = Field(default_factory=lambda: [
        "finance-agent (v1.2.0, high-risk, policy: finance-v3)",
        "support-agent (v1.1.0, medium-risk, policy: support-v1)",
        "sales-agent (v1.0.0, high-risk, policy: sales-v1)"
    ])

def get_agbom_inventory(settings: Optional[Settings] = None) -> dict[str, Any]:
    s = settings or Settings()
    agbom = AgentBillOfMaterials(
        environment=s.app_env.value,
        model=s.gemini_model,
        project_id=s.google_cloud_project,
        state_store="Google Cloud Firestore" if s.google_cloud_project != "approval-loop-hackathon" else "In-Memory / Firestore (Configurable)"
    )
    return agbom.model_dump()
