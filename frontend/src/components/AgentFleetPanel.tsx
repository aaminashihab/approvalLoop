import React from 'react';
import { Bot, ShieldCheck, KeyRound } from 'lucide-react';
import { AgentRegistration } from '../types/approval';

interface AgentFleetPanelProps {
  agents: AgentRegistration[];
}

export const AgentFleetPanel: React.FC<AgentFleetPanelProps> = ({ agents }) => {
  const getRiskBadge = (risk: string) => {
    switch (risk) {
      case 'critical':
        return 'bg-rose-900/60 text-rose-300 border-rose-700';
      case 'high':
        return 'bg-amber-900/60 text-amber-300 border-amber-700';
      case 'medium':
        return 'bg-sky-900/60 text-sky-300 border-sky-700';
      default:
        return 'bg-emerald-900/60 text-emerald-300 border-emerald-700';
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-indigo-600/30 border border-indigo-500/40">
            <Bot className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white tracking-wide uppercase">Institutional Agent Fleet</h2>
            <p className="text-xs text-slate-400">
              Registered Institutional AI Agents • Governed by ApprovalLoop Gateway
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-2.5 py-1 bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs font-mono font-semibold rounded-md flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            Zero-Trust Registry (Active)
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {agents.map((agent) => (
          <div
            key={agent.agent_id}
            className="bg-slate-950 border border-slate-800 hover:border-slate-700 rounded-xl p-4 transition-all hover:shadow-lg flex flex-col justify-between space-y-3"
          >
            <div>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                    {agent.name}
                  </h3>
                  <p className="text-xs font-mono text-indigo-400 mt-0.5">
                    {agent.agent_id} • v{agent.version}
                  </p>
                </div>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${getRiskBadge(agent.risk_level)}`}>
                  {agent.risk_level} Risk
                </span>
              </div>

              <p className="text-xs text-slate-400 mt-2 line-clamp-2">
                {agent.description}
              </p>
            </div>

            <div className="space-y-2 pt-2 border-t border-slate-800/80 text-xs font-mono">
              <div className="flex items-center justify-between text-slate-400">
                <span>Policy Profile:</span>
                <span className="text-amber-400 font-semibold">{agent.policy_profile}</span>
              </div>
              <div className="flex items-center justify-between text-slate-400">
                <span>Identity Credential:</span>
                <span className="text-emerald-400 flex items-center gap-1">
                  <KeyRound className="w-3 h-3" /> Verified HMAC/OIDC
                </span>
              </div>
              <div className="pt-1">
                <span className="text-slate-400 block text-[11px] mb-1 font-sans font-semibold">Allowed Actions:</span>
                <div className="flex flex-wrap gap-1">
                  {agent.allowed_actions.map((act) => (
                    <span
                      key={act}
                      className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px]"
                    >
                      {act}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
