import os
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

class AppEnvironment(str, Enum):
    TEST = "test"
    DEMO = "demo"
    PRODUCTION = "production"

class ThresholdConfig(BaseModel):
    nudge_threshold_seconds: int
    escalation_threshold_seconds: int
    scheduler_frequency_seconds: int

ENV_THRESHOLDS: dict[AppEnvironment, ThresholdConfig] = {
    AppEnvironment.TEST: ThresholdConfig(
        nudge_threshold_seconds=2,
        escalation_threshold_seconds=5,
        scheduler_frequency_seconds=1,
    ),
    AppEnvironment.DEMO: ThresholdConfig(
        nudge_threshold_seconds=30,
        escalation_threshold_seconds=90,
        scheduler_frequency_seconds=15,  # In-browser fast polling / demo tick
    ),
    AppEnvironment.PRODUCTION: ThresholdConfig(
        nudge_threshold_seconds=24 * 3600,       # 24 hours
        escalation_threshold_seconds=72 * 3600,  # 72 hours
        scheduler_frequency_seconds=60,          # 1-minute standard cron
    ),
}

class Settings(BaseModel):
    app_env: AppEnvironment = Field(
        default_factory=lambda: AppEnvironment(os.getenv("APP_ENV", "demo").lower())
    )
    admin_fallback_email: str = Field(
        default_factory=lambda: os.getenv("ADMIN_FALLBACK_EMAIL", "escalations-owner@company.internal")
    )
    scheduler_api_key: str = Field(
        default_factory=lambda: os.getenv("SCHEDULER_API_KEY", "dev-scheduler-secret-key")
    )
    agent_identity_secret: str = Field(
        default_factory=lambda: os.getenv("AGENT_IDENTITY_SECRET", "fleet-identity-master-secret-key-2026")
    )
    allowed_origins_raw: str = Field(
        default_factory=lambda: os.getenv("APP_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:8080,http://127.0.0.1:8080,http://127.0.0.1:5173")
    )
    google_cloud_project: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", "model-factor-506215-v8")
    )
    oidc_expected_audience: str | None = Field(
        default_factory=lambda: os.getenv("OIDC_EXPECTED_AUDIENCE")
    )
    gemini_api_key: str | None = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY")
    )
    gemini_model: str = Field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    )
    allow_insecure_demo_auth: bool = Field(
        default_factory=lambda: os.getenv("ALLOW_INSECURE_DEMO_AUTH", "false").lower() in ("true", "1", "yes")
    )
    model_armor_enabled: bool = Field(
        default_factory=lambda: os.getenv("MODEL_ARMOR_ENABLED", "true").lower() in ("true", "1", "yes")
    )
    model_armor_fail_closed: bool = Field(
        default_factory=lambda: os.getenv("MODEL_ARMOR_FAIL_CLOSED", "true").lower() in ("true", "1", "yes")
    )
    model_armor_location: str = Field(
        default_factory=lambda: os.getenv("MODEL_ARMOR_LOCATION", os.getenv("REGION", "us-central1"))
    )
    model_armor_template_id: str = Field(
        default_factory=lambda: os.getenv("MODEL_ARMOR_TEMPLATE_ID", "default-guardrail")
    )
    firestore_collection_reports: str = "expense_reports"
    firestore_collection_actions: str = "approval_actions"
    firestore_collection_agents: str = "agent_registry"
    firestore_collection_memory: str = "workflow_memories"

    @property
    def thresholds(self) -> ThresholdConfig:
        return ENV_THRESHOLDS[self.app_env]

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins_raw.split(",") if o.strip()]

    def model_post_init(self, __context: Any) -> None:
        self.validate_production_safety()

    def validate_production_safety(self):
        """Hard production-hardening validation guards."""
        if self.app_env == AppEnvironment.PRODUCTION:
            if self.allow_insecure_demo_auth:
                raise ValueError("PRODUCTION error: ALLOW_INSECURE_DEMO_AUTH cannot be enabled when APP_ENV=production.")
            if not self.admin_fallback_email or "example.com" in self.admin_fallback_email:
                raise ValueError("PRODUCTION error: ADMIN_FALLBACK_EMAIL must be a configured corporate escalation address.")
            if self.scheduler_api_key == "dev-scheduler-secret-key":
                raise ValueError("PRODUCTION error: Default development SCHEDULER_API_KEY is prohibited in production.")
            if self.agent_identity_secret == "fleet-identity-master-secret-key-2026":
                raise ValueError("PRODUCTION error: Default AGENT_IDENTITY_SECRET is prohibited in production.")
            if not self.gemini_api_key:
                raise ValueError("PRODUCTION error: GEMINI_API_KEY must be provided via environment variable or Google Secret Manager.")
            if self.google_cloud_project == "approval-loop-hackathon" and not os.getenv("GOOGLE_CLOUD_PROJECT"):
                raise ValueError("PRODUCTION error: GOOGLE_CLOUD_PROJECT must be explicitly configured in production.")
            if "*" in self.allowed_origins_raw:
                raise ValueError("PRODUCTION error: Wildcard '*' CORS origin is prohibited in production.")
