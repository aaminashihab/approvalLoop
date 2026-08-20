import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { ExpenseReport, ActionRecord, AutonomyMetrics } from '../types/approval';
import { AutonomyProof } from '../components/AutonomyProof';
import { ReportTable } from '../components/ReportTable';
import { ActionLedger } from '../components/ActionLedger';
import { StateMachine } from '../components/StateMachine';
import { ScenarioRunner } from '../components/ScenarioRunner';
import { Layers } from 'lucide-react';

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
  const [isLiveMode, setIsLiveMode] = useState<boolean>(true);

  // Read-only dashboard polling (purely observational, zero tick side-effects)
  const fetchData = async () => {
    try {
      const [r, a, m] = await Promise.all([
        api.getReports(),
        api.getActions(),
        api.getMetrics()
      ]);
      setReports(r);
      setActions(a);
      setMetrics(m);
    } catch (e) {
      console.error('Failed to fetch data', e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  // Manual Demo / Verification Handlers
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
              <h1 className="text-2xl font-black tracking-tight text-white">ApprovalLoop</h1>
              <p className="text-xs text-indigo-300 font-semibold">
                Bounded Autonomous Agent for Stalled Human Workflows — Powered by Google Gemini & Cloud Run
              </p>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-2 italic">
            "Most agents wait for a prompt. ApprovalLoop acts when nothing happens."
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300 flex items-center gap-2.5 font-mono shadow-md">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
            Autonomous Trigger: <span className="text-emerald-400 font-bold">Cloud Scheduler (Active)</span>
          </div>
        </div>
      </div>

      {/* AUTONOMY PROOF SECTION */}
      <AutonomyProof metrics={metrics} isLiveMode={isLiveMode} />

      {/* Controls & Scenario Simulation */}
      <ScenarioRunner
        onTick={handleTick}
        onSeed={handleSeed}
        onAdvanceTime={handleAdvanceTime}
        onSimulateRace={handleSimulateRace}
        onSimulateAdversarial={handleSimulateAdversarial}
        isLiveMode={isLiveMode}
        onToggleLiveMode={() => setIsLiveMode(!isLiveMode)}
      />

      {/* State Machine Diagram */}
      <StateMachine />

      {/* Reports Table & Action Ledger */}
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
