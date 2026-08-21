import pytest
from approval_loop.memory.memory_bank import (
    MemoryBankService, WorkflowMemoryRecord, WorkflowState
)
from approval_loop.storage.memory_repo import InMemoryRepository

def test_memory_bank_lifecycle_and_resumption():
    repo = InMemoryRepository()
    service = MemoryBankService(repo=repo)
    
    # 1. Initialize workflow
    rec = WorkflowMemoryRecord(
        workflow_id="wf_async_900",
        agent_id="finance-agent",
        session_id="sess_client_44",
        state=WorkflowState.INITIALIZED
    )
    service.save_workflow(rec)
    
    # 2. Pause for approval
    service.pause_for_approval(
        workflow_id="wf_async_900",
        action_id="act_gw_888",
        reason="Requires Director Sign-off",
        policy_version="finance-v3.2.0"
    )
    
    paused = service.get_workflow("wf_async_900")
    assert paused is not None
    assert paused.state == WorkflowState.PAUSED_FOR_APPROVAL
    assert paused.approval_record.status == "pending"
    assert paused.paused_at is not None
    
    # 3. Simulate asynchronous resumption after human sign-off
    service.resume_workflow(
        workflow_id="wf_async_900",
        approved=True,
        operator="Director Marcus",
        notes="Approved after budget check"
    )
    
    resumed = service.get_workflow("wf_async_900")
    assert resumed.state == WorkflowState.APPROVED
    assert resumed.approval_record.status == "approved"
    assert resumed.approval_record.decided_by == "Director Marcus"
    assert resumed.resumed_at is not None
    
    # 4. Complete workflow
    service.complete_workflow("wf_async_900", {"status": "SUCCESS", "receipt": "notif_999"})
    completed = service.get_workflow("wf_async_900")
    assert completed.state == WorkflowState.COMPLETED
    assert len(completed.tool_results) == 1

def test_memory_isolation_by_agent():
    service = MemoryBankService()
    service.save_workflow(WorkflowMemoryRecord(workflow_id="wf_1", agent_id="finance-agent"))
    service.save_workflow(WorkflowMemoryRecord(workflow_id="wf_2", agent_id="support-agent"))
    service.save_workflow(WorkflowMemoryRecord(workflow_id="wf_3", agent_id="finance-agent"))
    
    finance_wfs = service.list_workflows(agent_id="finance-agent")
    assert len(finance_wfs) == 2
    assert all(w.agent_id == "finance-agent" for w in finance_wfs)
    
    support_wfs = service.list_workflows(agent_id="support-agent")
    assert len(support_wfs) == 1
    assert support_wfs[0].agent_id == "support-agent"
