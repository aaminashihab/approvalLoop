import pytest
from datetime import timedelta
from decimal import Decimal
from approval_loop.domain.agent_registry import AgentRegistryService
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext, utc_now
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.memory.memory_bank import MemoryBankService
from approval_loop.worker.worker import MockNotificationProvider
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.runtime.async_runtime import AsyncAgentRuntime, AsyncTaskState

@pytest.fixture
def setup_runtime():
    registry = AgentRegistryService()
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="runtime-test-secret")
    policy = PolicyEngine()
    memory_bank = MemoryBankService()
    worker = MockNotificationProvider()
    
    gateway = AgentGateway(
        registry=registry,
        identity_provider=id_provider,
        policy_engine=policy,
        memory_bank=memory_bank,
        worker=worker,
        guardrail=ModelSafetyGuardrail()
    )
    runtime = AsyncAgentRuntime(gateway=gateway, memory_bank=memory_bank, lease_duration_seconds=2)
    return runtime, id_provider, gateway

def test_async_workflow_submission_and_idempotency(setup_runtime):
    runtime, id_provider, _ = setup_runtime
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-505",
        amount=Decimal("1000.00"),
        currency="INR",
        recipient="user@company.com"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    task1, dec1 = runtime.submit_workflow(proposal, auth_ctx)
    assert task1.status == AsyncTaskState.QUEUED
    
    # Duplicate submission with same logical action
    task2, dec2 = runtime.submit_workflow(proposal, auth_ctx)
    assert task2.task_id == task1.task_id  # Idempotent deduplication

def test_leased_claiming_and_crash_recovery(setup_runtime):
    runtime, id_provider, _ = setup_runtime
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-606",
        amount=Decimal("1000.00"),
        currency="INR",
        recipient="user@company.com"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    task, _ = runtime.submit_workflow(proposal, auth_ctx)
    
    # Worker 1 claims task
    claimed = runtime.claim_next_task(worker_id="worker-node-A")
    assert claimed is not None
    assert claimed.task_id == task.task_id
    assert claimed.status == AsyncTaskState.LEASED
    assert claimed.attempt_count == 1
    
    # Simulate worker crash: lease expires in past
    claimed.lease_expires_at = utc_now() - timedelta(seconds=5)
    
    # Crash Recovery routine runs
    recovered = runtime.recover_expired_leases()
    assert len(recovered) == 1
    assert recovered[0].task_id == task.task_id
    assert recovered[0].status == AsyncTaskState.RETRY_PENDING
