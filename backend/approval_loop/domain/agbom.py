from typing import Any, Optional
from pydantic import BaseModel, Field
from approval_loop.config import Settings

class AgentBillOfMaterials(BaseModel):
    """
    Declared Runtime Dependency and Safety Inventory (AgBOM):
    Provides a standardized declaration of models, tools, datastores, safety gates, and runtime dependencies.
    """
    agent_name: str = "ApprovalLoop"
    version: str = "1.0.0"
    track: str = "Taskmaster"
    environment: str = "demo"
    model: str = "gemini-3.5-flash"
    framework: str = "Google GenAI SDK (google-genai)"
    runtime: str = "Google Cloud Run"
    project_id: str = "approval-loop-hackathon"
    trigger: str = "Google Cloud Scheduler (* * * * *)"
    data_sources: list[str] = Field(default_factory=lambda: ["expense_reports", "approver_registry"])
    state_store: str = "Google Cloud Firestore"
    tools: list[str] = Field(default_factory=lambda: ["notification_worker", "firestore_transaction_outbox"])
    safety_mechanisms: list[str] = Field(default_factory=lambda: [
        "deterministic_state_machine",
        "4_point_safety_validator",
        "corporate_policy_engine",
        "transactional_outbox_claiming",
        "scenario_13_conditional_transition_guard",
        "decimal_financial_precision"
    ])
    skills: list[str] = Field(default_factory=lambda: ["approval_escalation"])

def get_agbom_inventory(settings: Optional[Settings] = None) -> dict[str, Any]:
    s = settings or Settings()
    agbom = AgentBillOfMaterials(
        environment=s.app_env.value,
        model=s.gemini_model,
        project_id=s.google_cloud_project,
        state_store="Google Cloud Firestore" if s.google_cloud_project != "approval-loop-hackathon" else "In-Memory / Firestore (Configurable)"
    )
    return agbom.model_dump()
