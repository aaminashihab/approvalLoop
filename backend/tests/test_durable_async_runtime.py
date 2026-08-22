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
from approval_loop.storage.memory_repo import InMemoryRepository

@pytest.fixture
def setup_durable_runtime():
    repo = InMemoryRepository()
    registry = AgentRegistryService(repo=repo)
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="durable-test-secret")
    policy = PolicyEngine()
    memory_bank = MemoryBankService(repo=repo)
    worker = MockNotificationProvider()
    
    gateway = AgentGateway(
        registry=registry,
        identity_provider=id_provider,
        policy_engine=policy,
        memory_bank=memory_bank,
        worker=worker,
        guardrail=ModelSafetyGuardrail()
    )
    runtime = AsyncAgentRuntime(gateway=gateway, memory_bank=memory_bank, lease_duration_seconds=2, repo=repo)
    return runtime, id_provider, gateway, repo, memory_bank, worker

def test_task_persistence_and_restart_recovery(setup_durable_runtime):
    runtime, id_provider, gateway, repo, memory_bank, worker = setup_durable_runtime
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-DURABLE-1",
        amount=Decimal("1200.00"),
        currency="INR",
        recipient="client@company.com"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    # 1. Submit workflow to runtime
    task1, dec1 = runtime.submit_workflow(proposal, auth_ctx)
    assert task1.status == AsyncTaskState.QUEUED
    
    # 2. Simulate Cloud Run Instance Restart: Instantiate a brand-new AsyncAgentRuntime over the same repository
    restarted_runtime = AsyncAgentRuntime(gateway=gateway, memory_bank=memory_bank, lease_duration_seconds=2, repo=repo)
    
    # Check that task survived process restart
    tasks = restarted_runtime.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].task_id == task1.task_id
    assert tasks[0].idempotency_key == task1.idempotency_key
    
    # Claim task on restarted instance
    claimed = restarted_runtime.claim_next_task(worker_id="cloud-run-worker-2")
    assert claimed is not None
    assert claimed.task_id == task1.task_id
    assert claimed.status == AsyncTaskState.LEASED
    
    # Complete task
    completed = restarted_runtime.complete_task(claimed.task_id, {"status": "success"})
    assert completed.status == AsyncTaskState.COMPLETED
    
    # Verify persisted in repo
    stored = repo.get_async_task(task1.task_id)
    assert stored.status == AsyncTaskState.COMPLETED

def test_lease_expiration_crash_recovery_durable(setup_durable_runtime):
    runtime, id_provider, gateway, repo, memory_bank, worker = setup_durable_runtime
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-DURABLE-2",
        amount=Decimal("1400.00"),
        currency="INR",
        recipient="client2@company.com"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    task, _ = runtime.submit_workflow(proposal, auth_ctx)
    claimed = runtime.claim_next_task(worker_id="worker-A")
    
    # Simulate worker crash & time lapse
    claimed.lease_expires_at = utc_now() - timedelta(seconds=10)
    repo.save_async_task(claimed)
    
    # Simulated restart / recovery sweep
    restarted_runtime = AsyncAgentRuntime(gateway=gateway, memory_bank=memory_bank, lease_duration_seconds=2, repo=repo)
    recovered = restarted_runtime.recover_expired_leases()
    assert len(recovered) == 1
    assert recovered[0].status == AsyncTaskState.RETRY_PENDING
