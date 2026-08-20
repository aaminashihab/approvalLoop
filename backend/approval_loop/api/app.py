import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from approval_loop.config import Settings
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.storage.memory_repo import InMemoryRepository
from approval_loop.storage.firestore_repo import FirestoreRepository
from approval_loop.agent.drafter import GeminiAgentDrafter
from approval_loop.validator.validator import DeterministicValidator
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.observability.tracer import OpenTelemetryTracer
from approval_loop.worker.worker import MockNotificationWorker
from approval_loop.engine import ApprovalEngine
from approval_loop.api.routes import router, set_engine_instance, set_settings_instance

settings = Settings()

if os.getenv("USE_FIRESTORE", "false").lower() == "true":
    repo = FirestoreRepository(project_id=settings.google_cloud_project)
else:
    repo = InMemoryRepository()

registry = ApproverRegistry(admin_fallback_email=settings.admin_fallback_email)
registry.register_approver("sarah.finance@company.com", "marcus.director@company.com")
registry.register_approver("approver1@co.com", "backup1@co.com")

drafter = GeminiAgentDrafter(api_key=settings.gemini_api_key, model=settings.gemini_model)
validator = DeterministicValidator(registry=registry)
policy_engine = PolicyEngine(settings=settings)
tracer = OpenTelemetryTracer.get_tracer()
worker = MockNotificationWorker()

engine = ApprovalEngine(
    repo=repo,
    settings=settings,
    registry=registry,
    drafter=drafter,
    validator=validator,
    worker=worker,
    policy_engine=policy_engine,
    tracer=tracer
)

set_engine_instance(engine)
set_settings_instance(settings)

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_production_safety()
    yield

app = FastAPI(
    title="ApprovalLoop API",
    description="Autonomous Approval Chasing Agent — Acts when nothing happens.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/healthz")
def healthz():
    return {
        "status": "healthy",
        "app_env": settings.app_env.value,
        "storage": "firestore" if isinstance(repo, FirestoreRepository) else "in-memory",
        "project": settings.google_cloud_project,
        "gemini_model": settings.gemini_model,
        "framework": "Google GenAI SDK (google-genai)"
    }

# Mount static frontend build
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist"))
static_dir = os.path.abspath("/app/static")
mount_dir = frontend_dist if os.path.exists(frontend_dist) else (static_dir if os.path.exists(static_dir) else None)
if mount_dir:
    app.mount("/", StaticFiles(directory=mount_dir, html=True), name="static")
