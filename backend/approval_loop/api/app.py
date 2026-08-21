import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from approval_loop.config import Settings, AppEnvironment
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.domain.agent_registry import AgentRegistryService
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.memory.memory_bank import MemoryBankService
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.runtime.async_runtime import AsyncAgentRuntime
from approval_loop.storage.memory_repo import InMemoryRepository
from approval_loop.storage.firestore_repo import FirestoreRepository
from approval_loop.agent.drafter import GeminiAgentDrafter
from approval_loop.agent.fleet import FinanceAgent, SupportAgent, SalesAgent
from approval_loop.validator.validator import DeterministicValidator
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.observability.tracer import OpenTelemetryTracer
from approval_loop.worker.worker import MockNotificationWorker
from approval_loop.engine import ApprovalEngine
from approval_loop.api.routes import (
    router, set_engine_instance, set_settings_instance,
    set_gateway_instance, set_registry_service_instance,
    set_memory_bank_instance, set_runtime_instance, set_fleet_instances
)

settings = Settings()

if os.getenv("USE_FIRESTORE", "false").lower() == "true":
    repo = FirestoreRepository(project_id=settings.google_cloud_project)
else:
    repo = InMemoryRepository()

# 1. Approver Registry & Agent Registry
approver_registry = ApproverRegistry(admin_fallback_email=settings.admin_fallback_email)
approver_registry.register_approver("sarah.finance@company.com", "marcus.director@company.com")
approver_registry.register_approver("approver1@co.com", "backup1@co.com")

agent_registry_service = AgentRegistryService(repo=repo)

# 2. Identity Provider & Model Safety Guardrail
identity_provider = AgentIdentityProvider(
    registry_service=agent_registry_service,
    secret_key=settings.agent_identity_secret
)
guardrail = ModelSafetyGuardrail()

# 3. Memory Bank & Policy Engine
memory_bank_service = MemoryBankService(repo=repo)
policy_engine = PolicyEngine(settings=settings)
tracer = OpenTelemetryTracer.get_tracer()
worker = MockNotificationWorker()

# 4. Agent Gateway & Async Runtime
gateway = AgentGateway(
    registry=agent_registry_service,
    identity_provider=identity_provider,
    policy_engine=policy_engine,
    memory_bank=memory_bank_service,
    worker=worker,
    guardrail=guardrail,
    tracer=tracer
)
runtime = AsyncAgentRuntime(gateway=gateway, memory_bank=memory_bank_service)

# 5. Gemini Agent Fleet
finance_agent = FinanceAgent(identity_provider=identity_provider, api_key=settings.gemini_api_key, model=settings.gemini_model)
support_agent = SupportAgent(identity_provider=identity_provider, api_key=settings.gemini_api_key, model=settings.gemini_model)
sales_agent = SalesAgent(identity_provider=identity_provider, api_key=settings.gemini_api_key, model=settings.gemini_model)

# 6. Core ApprovalEngine for autonomous background expense chasing
drafter = GeminiAgentDrafter(api_key=settings.gemini_api_key, model=settings.gemini_model)
validator = DeterministicValidator(registry=approver_registry)

engine = ApprovalEngine(
    repo=repo,
    settings=settings,
    registry=approver_registry,
    drafter=drafter,
    validator=validator,
    worker=worker,
    policy_engine=policy_engine,
    tracer=tracer
)

# Wire instances to routes
set_engine_instance(engine)
set_settings_instance(settings)
set_gateway_instance(gateway)
set_registry_service_instance(agent_registry_service)
set_memory_bank_instance(memory_bank_service)
set_runtime_instance(runtime)
set_fleet_instances(finance_agent, support_agent, sales_agent)

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_production_safety()
    yield

app = FastAPI(
    title="ApprovalLoop — Fortified Enterprise Fleet Gateway",
    description="Deterministic execution governance gateway for autonomous AI agent fleets. AI proposes. Policy decides. Infrastructure executes.",
    version="2.1.0",
    lifespan=lifespan
)

# Strict CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins if settings.app_env == AppEnvironment.PRODUCTION else ["*"],
    allow_credentials=True if settings.app_env != AppEnvironment.PRODUCTION else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Production Health Check Endpoints (Requirement 16)
@app.get("/health/live")
def health_live():
    """Liveness check: process is responsive."""
    return {"status": "alive", "service": "approval-loop-gateway"}

@app.get("/health/ready")
def health_ready():
    """Readiness check: all dependencies, registry, and configuration are healthy."""
    try:
        # Check storage readiness
        repo_type = "firestore" if isinstance(repo, FirestoreRepository) else "in-memory"
        # Check registry readiness
        agents = agent_registry_service.list_agents()
        return {
            "status": "ready",
            "environment": settings.app_env.value,
            "storage": repo_type,
            "agents_registered": len(agents),
            "gateway": "active",
            "gemini_model": settings.gemini_model
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service not ready: {str(e)}"
        )

@app.get("/healthz")
def healthz():
    """Backward-compatible health endpoint."""
    return {
        "status": "healthy",
        "app_env": settings.app_env.value,
        "storage": "firestore" if isinstance(repo, FirestoreRepository) else "in-memory",
        "project": settings.google_cloud_project,
        "gemini_model": settings.gemini_model,
        "framework": "Google GenAI SDK (google-genai)",
        "gateway_version": "2.1.0"
    }

# Mount static frontend build
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist"))
static_dir = os.path.abspath("/app/static")
mount_dir = frontend_dist if os.path.exists(frontend_dist) else (static_dir if os.path.exists(static_dir) else None)
if mount_dir:
    app.mount("/", StaticFiles(directory=mount_dir, html=True), name="static")
