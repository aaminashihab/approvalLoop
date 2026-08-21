import React, { useState } from 'react';
import { Zap, ShieldCheck, XCircle, Sparkles, CheckCircle2, UserCheck } from 'lucide-react';
import { api } from '../api/client';
import { GatewayDecision } from '../types/approval';

interface CriticalDemoRunnerProps {
  onWorkflowTriggered: () => void;
}

export const CriticalDemoRunner: React.FC<CriticalDemoRunnerProps> = ({ onWorkflowTriggered }) => {
  const [activeResult, setActiveResult] = useState<{
    scenario: string;
    expected: string;
    proposal: any;
    decision: GatewayDecision;
  } | null>(null);
  const [loadingCase, setLoadingCase] = useState<string | null>(null);

  const handleCaseA = async () => {
    setLoadingCase('A');
    try {
      const res = await api.triggerScenarioA();
      setActiveResult({
        scenario: 'Case A: Low-Risk Financial Refund (< ₹5,000 / $50)',
        expected: 'ALLOW → Automatic Execution',
        proposal: res.proposal,
        decision: res.decision
      });
      onWorkflowTriggered();
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingCase(null);
    }
  };

  const handleCaseB = async () => {
    setLoadingCase('B');
    try {
      const res = await api.triggerScenarioB();
      setActiveResult({
        scenario: 'Case B: Medium-Risk Financial Refund (₹5,000 – ₹25,000 / $50 – $250)',
        expected: 'REQUIRE_HUMAN_APPROVAL → Paused in Memory Bank → Awaiting Sign-Off',
        proposal: res.proposal,
        decision: res.decision
      });
      onWorkflowTriggered();
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingCase(null);
    }
  };

  const handleCaseC = async () => {
    setLoadingCase('C');
    try {
      const res = await api.triggerScenarioC();
      setActiveResult({
        scenario: 'Case C: High-Risk Financial Refund (> ₹25,000 / $250)',
        expected: 'DENY → Deterministic Policy Reject (LLM Cannot Override)',
        proposal: res.proposal,
        decision: res.decision
      });
      onWorkflowTriggered();
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingCase(null);
    }
  };

  const getDecisionBadge = (decision: string) => {
    switch (decision) {
      case 'allow':
        return 'bg-emerald-950/80 text-emerald-300 border-emerald-700';
      case 'require_human_approval':
        return 'bg-amber-950/80 text-amber-300 border-amber-700';
      case 'deny':
        return 'bg-rose-950/80 text-rose-300 border-rose-700';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-indigo-600/30 border border-indigo-500/40">
            <Zap className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white tracking-wide uppercase">Critical Demo Scenarios</h2>
            <p className="text-xs text-slate-400">
              Live Governance Proof: "AI proposes. Deterministic policy decides. Infrastructure executes."
            </p>
          </div>
        </div>

        <span className="px-2.5 py-1 bg-indigo-950/60 border border-indigo-800 text-indigo-300 text-xs font-mono font-semibold rounded-md flex items-center gap-1">
          <Sparkles className="w-3.5 h-3.5" /> 3-Tier Policy Proof
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Case A */}
        <button
          onClick={handleCaseA}
          disabled={loadingCase !== null}
          className="p-3.5 bg-slate-950 hover:bg-slate-800/80 border border-emerald-800/60 hover:border-emerald-600 text-left rounded-xl transition-all shadow-md group disabled:opacity-50"
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950 border border-emerald-700 text-emerald-300 uppercase">
              Case A • Auto-ALLOW
            </span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <h4 className="text-sm font-bold text-white group-hover:text-emerald-300 transition-colors">
            Refund ₹2,000
          </h4>
          <p className="text-xs text-slate-400 mt-1">
            Low-risk financial operation. Policy allows instant autonomous execution.
          </p>
        </button>

        {/* Case B */}
        <button
          onClick={handleCaseB}
          disabled={loadingCase !== null}
          className="p-3.5 bg-slate-950 hover:bg-slate-800/80 border border-amber-800/60 hover:border-amber-600 text-left rounded-xl transition-all shadow-md group disabled:opacity-50"
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-950 border border-amber-700 text-amber-300 uppercase">
              Case B • Human Sign-Off
            </span>
            <UserCheck className="w-4 h-4 text-amber-400" />
          </div>
          <h4 className="text-sm font-bold text-white group-hover:text-amber-300 transition-colors">
            Refund ₹20,000
          </h4>
          <p className="text-xs text-slate-400 mt-1">
            Medium-risk threshold. Workflow pauses in Memory Bank waiting for Human-in-the-Loop.
          </p>
        </button>

        {/* Case C */}
        <button
          onClick={handleCaseC}
          disabled={loadingCase !== null}
          className="p-3.5 bg-slate-950 hover:bg-slate-800/80 border border-rose-800/60 hover:border-rose-600 text-left rounded-xl transition-all shadow-md group disabled:opacity-50"
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-950 border border-rose-700 text-rose-300 uppercase">
              Case C • Policy DENY
            </span>
            <XCircle className="w-4 h-4 text-rose-400" />
          </div>
          <h4 className="text-sm font-bold text-white group-hover:text-rose-300 transition-colors">
            Refund ₹100,000
          </h4>
          <p className="text-xs text-slate-400 mt-1">
            High-risk ceiling violation. Blocked deterministically even if Gemini recommended it.
          </p>
        </button>
      </div>

      {/* Live Decision Card */}
      {activeResult && (
        <div className="mt-4 p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-3 animate-in fade-in duration-200">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
            <div>
              <span className="text-[10px] font-mono text-indigo-400 uppercase tracking-wider font-bold block">
                Live Gateway Decision Breakdown
              </span>
              <h3 className="text-sm font-bold text-white">{activeResult.scenario}</h3>
            </div>
            <span className={`px-3 py-1 rounded text-xs font-mono font-bold uppercase tracking-wider border ${getDecisionBadge(activeResult.decision.decision)}`}>
              {activeResult.decision.decision.replace('_', ' ')}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
            <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
              <span className="text-slate-500 block text-[10px]">Agent Identity:</span>
              <span className="text-emerald-400 font-bold flex items-center gap-1">
                <ShieldCheck className="w-3 h-3" /> VERIFIED (HMAC)
              </span>
            </div>
            <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
              <span className="text-slate-500 block text-[10px]">Policy Profile:</span>
              <span className="text-amber-400 font-bold">{activeResult.decision.policy_version}</span>
            </div>
            <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
              <span className="text-slate-500 block text-[10px]">Risk Tier:</span>
              <span className="text-slate-200 font-bold uppercase">{activeResult.decision.risk_level}</span>
            </div>
            <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
              <span className="text-slate-500 block text-[10px]">Human Sign-Off:</span>
              <span className="text-white font-bold">{activeResult.decision.requires_human_approval ? 'REQUIRED' : 'NO'}</span>
            </div>
          </div>

          <div className="p-2.5 bg-slate-900/60 rounded-lg border border-slate-800/80 text-xs">
            <span className="text-slate-400 font-semibold block mb-0.5">Deterministic Reason:</span>
            <p className="text-slate-200 font-mono">{activeResult.decision.reason}</p>
          </div>
        </div>
      )}
    </div>
  );
};
