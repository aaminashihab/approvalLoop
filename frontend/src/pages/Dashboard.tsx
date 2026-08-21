import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import {
  ExpenseReport, ActionRecord, AutonomyMetrics, AgentRegistration,
  PendingAction, WorkflowMemoryRecord
} from '../types/approval';
import { AutonomyProof } from '../components/AutonomyProof';
import { SafetyProof } from '../components/SafetyProof';
import { ReportTable } from '../components/ReportTable';
import { ActionLedger } from '../components/ActionLedger';
import { StateMachine } from '../components/StateMachine';
import { ScenarioRunner } from '../components/ScenarioRunner';
import { AgentFleetPanel } from '../components/AgentFleetPanel';
import { HumanApprovalQueue } from '../components/HumanApprovalQueue';
import { CriticalDemoRunner } from '../components/CriticalDemoRunner';
import { MemoryBankViewer } from '../components/MemoryBankViewer';
import { ShieldCheck, Layers } from 'lucide-react';

export const Dashboard: React.FC = () => {
  const [reports, setReports] = useState<ExpenseReport[]>([]);
  const [actions, setActions] = useState<ActionRecord[]>([]);
  const [metrics, setMetrics] = useState<AutonomyMetrics>({
    last_wake_up: null,
    reports_observed: 0,
    eligible_reports: 0,
    actions_claimed: 0,
    notifications_sent: 0,
    escalations_count: 0,
    blocked_actions_count: 0,
    duplicate_actions_prevented: 0,
    unsafe_transitions_prevented: 0,
    human_prompts_required: 0
  });
  const [agents, setAgents] = useState<AgentRegistration[]>([]);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowMemoryRecord[]>([]);
  const [isLiveMode, setIsLiveMode] = useState<boolean>(true);

  const fetchData = async () => {
    try {
      const [r, a, m, ag, pa, wf] = await Promise.all([
        api.getReports(),
        api.getActions(),
        api.getMetrics(),
        api.getAgents().catch(() => []),
        api.getPendingActions().catch(() => []),
        api.getWorkflows().catch(() => [])
      ]);
      setReports(r);
      setActions(a);
      setMetrics(m);
      setAgents(ag);
      setPendingActions(pa);
      setWorkflows(wf);
    } catch (e) {
      console.error('Failed to fetch dashboard data', e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  // Handlers for Human Approval Queue
  const handleApprove = async (actionId: string, operator: string, notes: string) => {
    await api.approveAction(actionId, operator, notes);
    await fetchData();
  };

  const handleReject = async (actionId: string, operator: string, notes: string) => {
    await api.rejectAction(actionId, operator, notes);
    await fetchData();
  };

  // Handlers for Autonomous Tick and Scenarios
  const handleTick = async () => {
    await api.triggerTick();
    await fetchData();
  };

  const handleSeed = async () => {
    await api.seedData();
    await fetchData();
  };

  const handleAdvanceTime = async () => {
    await api.advanceTime(35);
    await fetchData();
  };

  const handleSimulateRace = async () => {
    await api.simulateRace();
    await fetchData();
  };

  const handleSimulateAdversarial = async () => {
    await api.simulateAdversarial();
    await fetchData();
  };

  const handleSimulateNotificationFailure = async () => {
    await api.simulateNotificationFailure();
    await fetchData();
  };

  const handleResetDemo = async () => {
    await api.resetDemo();
    await fetchData();
  };

  const handleResolve = async (id: string) => {
    await api.resolveReport(id);
    await fetchData();
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-600 shadow-lg shadow-indigo-600/30">
              <Layers className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-black tracking-tight text-white">ApprovalLoop</h1>
                <span className="px-2 py-0.5 rounded bg-indigo-950 border border-indigo-700 text-indigo-300 text-[11px] font-mono font-bold uppercase">
                  Fortified Enterprise Fleet
                </span>
              </div>
              <p className="text-xs text-indigo-300 font-semibold mt-0.5">
                Deterministic Execution Governance Gateway for Autonomous Agent Fleets — Powered by Google Gemini &amp; Cloud Run
              </p>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-2 font-mono font-semibold text-emerald-400">
            "AI proposes. Deterministic policy decides. Infrastructure executes."
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300 flex items-center gap-2 font-mono shadow-md">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            Cloud Scheduler: <span className="text-emerald-400 font-bold">Active</span>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300 flex items-center gap-2 font-mono shadow-md">
            <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
            Gateway: <span className="text-indigo-400 font-bold">Enforced</span>
          </div>
        </div>
      </div>

      {/* 1. AGENT FLEET PANEL */}
      <AgentFleetPanel agents={agents} />

      {/* 2. CRITICAL DEMO SCENARIOS (Case A, B, C) */}
      <CriticalDemoRunner onWorkflowTriggered={fetchData} />

      {/* 3. HUMAN-IN-THE-LOOP APPROVAL QUEUE */}
      <HumanApprovalQueue
        pendingActions={pendingActions}
        onApprove={handleApprove}
        onReject={handleReject}
      />

      {/* 4. AUTONOMY METRICS PROOF */}
      <AutonomyProof metrics={metrics} isLiveMode={isLiveMode} />

      {/* 5. MEMORY BANK VIEWER */}
      <MemoryBankViewer workflows={workflows} />

      {/* 6. SAFETY PROOF & CONTROL PLANE */}
      <SafetyProof />

      {/* 7. CONTROLS & TESTBEDS */}
      <ScenarioRunner
        onTick={handleTick}
        onSeed={handleSeed}
        onAdvanceTime={handleAdvanceTime}
        onSimulateRace={handleSimulateRace}
        onSimulateAdversarial={handleSimulateAdversarial}
        onSimulateNotificationFailure={handleSimulateNotificationFailure}
        onResetDemo={handleResetDemo}
        isLiveMode={isLiveMode}
        onToggleLiveMode={() => setIsLiveMode(!isLiveMode)}
      />

      {/* 8. STATE MACHINE & EXPENSE REPORTS */}
      <StateMachine />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5">
          <ReportTable reports={reports} onResolve={handleResolve} />
        </div>
        <div className="lg:col-span-7">
          <ActionLedger actions={actions} />
        </div>
      </div>
    </div>
  );
};
