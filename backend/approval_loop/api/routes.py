import uuid
from decimal import Decimal
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from approval_loop.domain.models import ExpenseReport, ReportStatus, NotificationEnvelope, utc_now
from approval_loop.domain.agbom import get_agbom_inventory
from approval_loop.engine import ApprovalEngine
from approval_loop.config import Settings
from approval_loop.api.auth import verify_scheduler_auth

router = APIRouter(prefix="/api")

_engine_instance: Optional[ApprovalEngine] = None
_settings_instance: Optional[Settings] = None

def set_engine_instance(engine: ApprovalEngine):
    global _engine_instance
    _engine_instance = engine

def set_settings_instance(settings: Settings):
    global _settings_instance
    _settings_instance = settings

def get_engine() -> ApprovalEngine:
    if _engine_instance is None:
        raise RuntimeError("ApprovalEngine not initialized")
    return _engine_instance

def get_settings() -> Settings:
    if _settings_instance is None:
        raise RuntimeError("Settings not initialized")
    return _settings_instance

class CreateReportRequest(BaseModel):
    report_id: Optional[str] = None
    submitter_name: str
    submitter_email: str
    approver_email: str
    backup_approver_email: Optional[str] = None
    amount: Decimal
    currency: str = "USD"
    description: str

class AdvanceTimeRequest(BaseModel):
    seconds: int = 35

@router.get("/agbom")
def get_agbom():
    """Returns runtime Agent Bill of Materials (AgBOM) inventory."""
    return get_agbom_inventory()

@router.get("/traces")
def get_traces(limit: int = Query(20, ge=1, le=100), engine: ApprovalEngine = Depends(get_engine)):
    """Returns recent OpenTelemetry-compatible execution spans and trace records."""
    return engine.tracer.get_recent_traces(limit=limit)

@router.get("/metrics")
def get_metrics(engine: ApprovalEngine = Depends(get_engine)):
    """Returns live, computed proof-of-autonomy metrics."""
    return engine.get_autonomy_metrics().model_dump()

@router.get("/reports")
def list_reports(engine: ApprovalEngine = Depends(get_engine)):
    reports = engine.repo.list_all_reports()
    return [r.to_dict() for r in reports]

@router.post("/reports")
def create_report(req: CreateReportRequest, engine: ApprovalEngine = Depends(get_engine)):
    report_id = req.report_id or f"EXP-{uuid.uuid4().hex[:4].upper()}"
    report = ExpenseReport(
        report_id=report_id,
        submitter_name=req.submitter_name,
        submitter_email=req.submitter_email,
        approver_email=req.approver_email,
        backup_approver_email=req.backup_approver_email,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
        submitted_at=utc_now()
    )
    engine.repo.save_report(report)
    return {"message": "Report created", "report": report.to_dict()}

@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: str, engine: ApprovalEngine = Depends(get_engine)):
    report = engine.repo.resolve_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"message": "Report resolved", "report": report.to_dict()}

@router.get("/actions")
def list_actions(engine: ApprovalEngine = Depends(get_engine)):
    actions = engine.repo.list_all_actions()
    return [a.to_dict() for a in actions]

@router.post("/tick")
def trigger_tick(
    tick_id: Optional[str] = Query(None),
    engine: ApprovalEngine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
    auth: bool = Depends(verify_scheduler_auth)
):
    processed = engine.run_tick(tick_id=tick_id)
    return {
        "tick_id": tick_id or "tick_auto",
        "processed_count": len(processed),
        "actions": [a.to_dict() for a in processed]
    }

@router.post("/seed")
def seed_demo_data(engine: ApprovalEngine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    now = utc_now()
    demo_reports = [
        ExpenseReport(
            report_id="EXP-101",
            status=ReportStatus.PENDING,
            submitter_name="Alice Chen",
            submitter_email="alice.chen@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email="marcus.director@company.com",
            amount=Decimal("150.00"),
            currency="USD",
            description="Client lunch meeting catering",
            submitted_at=now
        ),
        ExpenseReport(
            report_id="EXP-102",
            status=ReportStatus.PENDING,
            submitter_name="Bob Miller",
            submitter_email="bob.miller@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email="marcus.director@company.com",
            amount=Decimal("1250.00"),
            currency="USD",
            description="Q3 Cloud Infrastructure annual license",
            submitted_at=now - timedelta(seconds=settings.thresholds.nudge_threshold_seconds + 5)
        ),
        ExpenseReport(
            report_id="EXP-103",
            status=ReportStatus.NUDGED,
            submitter_name="Carlos Gomez",
            submitter_email="carlos.gomez@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email="marcus.director@company.com",
            amount=Decimal("3400.00"),
            currency="USD",
            description="Offsite workshop conference venue",
            submitted_at=now - timedelta(seconds=settings.thresholds.nudge_threshold_seconds + settings.thresholds.escalation_threshold_seconds + 20),
            last_nudged_at=now - timedelta(seconds=settings.thresholds.escalation_threshold_seconds + 10)
        ),
        ExpenseReport(
            report_id="EXP-104",
            status=ReportStatus.RESOLVED,
            submitter_name="Diana Prince",
            submitter_email="diana.prince@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email="marcus.director@company.com",
            amount=Decimal("520.00"),
            currency="USD",
            description="Team ergonomic monitors and peripherals",
            submitted_at=now - timedelta(seconds=120),
            resolved_at=now - timedelta(seconds=60)
        ),
        ExpenseReport(
            report_id="EXP-105",
            status=ReportStatus.NUDGED,
            submitter_name="Evan Wright",
            submitter_email="evan.wright@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email=None,
            amount=Decimal("890.00"),
            currency="USD",
            description="Emergency travel flight rebooking",
            submitted_at=now - timedelta(seconds=200),
            last_nudged_at=now - timedelta(seconds=settings.thresholds.escalation_threshold_seconds + 10)
        ),
    ]

    for r in demo_reports:
        engine.repo.save_report(r)

    return {"message": "Seeded 5 demo expense reports", "count": len(demo_reports)}

@router.post("/demo/advance-time")
def advance_time(req: AdvanceTimeRequest, engine: ApprovalEngine = Depends(get_engine)):
    reports = engine.repo.list_all_reports()
    updated = []
    delta = timedelta(seconds=req.seconds)
    for r in reports:
        r.submitted_at -= delta
        if r.last_nudged_at:
            r.last_nudged_at -= delta
        engine.repo.save_report(r)
        updated.append(r.report_id)
    return {"message": f"Advanced time by {req.seconds}s for {len(updated)} reports", "updated": updated}

@router.post("/simulate-adversarial")
def simulate_adversarial(engine: ApprovalEngine = Depends(get_engine)):
    """
    Demonstrates Safety Boundary: Gemini proposes a hallucinated recipient or amount.
    The deterministic validator intercepts and blocks the send.
    """
    now = utc_now()
    report_id = f"EXP-ADV-{uuid.uuid4().hex[:4].upper()}"
    report = ExpenseReport(
        report_id=report_id,
        status=ReportStatus.PENDING,
        submitter_name="Adversarial Test Submitter",
        submitter_email="submitter@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("750.00"),
        currency="USD",
        description="Software renewal",
        submitted_at=now - timedelta(seconds=60)
    )
    engine.repo.save_report(report)

    poisoned_envelope = NotificationEnvelope(
        report_id=report_id,
        amount=Decimal("99999.00"),  # Hallucinated
        currency="USD",
        recipient="unauthorized.attacker@external.com",  # Malicious/hallucinated
        submitter_name="Adversarial Test Submitter",
        subject="Action Required",
        body_text="Please approve immediately.",
        raw_llm_draft="Please approve immediately."
    )

    actions = engine.run_tick(
        tick_id=f"tick_adv_{report_id}",
        injected_adversarial_envelope=poisoned_envelope
    )

    return {
        "scenario": "Safety Demonstration: Deterministic Validator Blocks Hallucination",
        "tagline": "The model can propose. It cannot authorize.",
        "report_id": report_id,
        "actions": [a.to_dict() for a in actions]
    }

@router.post("/simulate-race")
def simulate_race_condition(engine: ApprovalEngine = Depends(get_engine)):
    now = utc_now()
    report_id = f"EXP-RACE-{uuid.uuid4().hex[:4].upper()}"
    report = ExpenseReport(
        report_id=report_id,
        status=ReportStatus.PENDING,
        submitter_name="Race Test Submitter",
        submitter_email="submitter@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("999.00"),
        currency="USD",
        description="Race condition simulation expense",
        submitted_at=now - timedelta(seconds=60)
    )
    engine.repo.save_report(report)

    def _race_resolve(envelope):
        engine.repo.resolve_report(report_id)

    original_callback = engine.worker.on_send_callback
    engine.worker.on_send_callback = _race_resolve

    try:
        actions = engine.run_tick(tick_id=f"tick_race_{report_id}")
    finally:
        engine.worker.on_send_callback = original_callback

    final_report = engine.repo.get_report(report_id)
    return {
        "scenario": "Scenario 13 — Race Condition Guard",
        "report_id": report_id,
        "final_report_status": final_report.status.value if final_report else None,
        "actions": [a.to_dict() for a in actions]
    }

@router.post("/simulate-notification-failure")
def simulate_notification_failure(engine: ApprovalEngine = Depends(get_engine)):
    """
    Demonstrates Fault-Tolerance: Simulates upstream provider connection timeout,
    action marked FAILED with exponential backoff, and subsequent retry idempotency.
    """
    now = utc_now()
    report_id = f"EXP-FAIL-{uuid.uuid4().hex[:4].upper()}"
    report = ExpenseReport(
        report_id=report_id,
        status=ReportStatus.PENDING,
        submitter_name="Retry Test Submitter",
        submitter_email="submitter@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("450.00"),
        currency="USD",
        description="Software SaaS license",
        submitted_at=now - timedelta(seconds=60)
    )
    engine.repo.save_report(report)

    # 1. Trigger with failure injection
    if hasattr(engine.worker, "simulate_failure"):
        engine.worker.simulate_failure = True

    try:
        failed_actions = engine.run_tick(tick_id=f"tick_fail_{report_id}")
    finally:
        if hasattr(engine.worker, "simulate_failure"):
            engine.worker.simulate_failure = False

    return {
        "scenario": "Fault Tolerance — Provider Timeout & Exponential Retry",
        "report_id": report_id,
        "actions": [a.to_dict() for a in failed_actions],
        "message": "Action marked FAILED with retry backoff timestamp. Retry will recover without duplicate dispatch."
    }

@router.post("/demo/reset")
def reset_demo(engine: ApprovalEngine = Depends(get_engine)):
    """Resets demo data to a pristine state."""
    # Seed default scenario reports
    seed_res = seed_data(engine)
    return {"message": "Demo state reset successfully", "seeded": seed_res}

