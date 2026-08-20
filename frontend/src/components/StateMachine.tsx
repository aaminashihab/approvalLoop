import React from 'react';
import { ArrowRight } from 'lucide-react';

export const StateMachine: React.FC = () => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl">
      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
        Formal State Machine & Invariants
      </h3>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="p-2.5 rounded-lg bg-amber-950/40 border border-amber-800/60 text-center flex-1 min-w-[120px]">
          <div className="font-bold text-amber-300">Pending</div>
          <div className="text-[10px] text-slate-400 mt-0.5">Submitted</div>
        </div>

        <div className="flex items-center text-slate-500 font-mono text-[10px]">
          nudge threshold <ArrowRight className="w-3.5 h-3.5 ml-1 text-indigo-400" />
        </div>

        <div className="p-2.5 rounded-lg bg-indigo-950/40 border border-indigo-800/60 text-center flex-1 min-w-[120px]">
          <div className="font-bold text-indigo-300">Nudged</div>
          <div className="text-[10px] text-slate-400 mt-0.5">Primary Notified</div>
        </div>

        <div className="flex items-center text-slate-500 font-mono text-[10px]">
          escalation threshold <ArrowRight className="w-3.5 h-3.5 ml-1 text-rose-400" />
        </div>

        <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-center flex-1 min-w-[120px]">
          <div className="font-bold text-rose-300">Escalated</div>
          <div className="text-[10px] text-slate-400 mt-0.5">Backup / Admin</div>
        </div>

        <div className="flex items-center text-slate-500 font-mono text-[10px]">
          sign off <ArrowRight className="w-3.5 h-3.5 ml-1 text-emerald-400" />
        </div>

        <div className="p-2.5 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-center flex-1 min-w-[120px]">
          <div className="font-bold text-emerald-300">Resolved</div>
          <div className="text-[10px] text-slate-400 mt-0.5">Terminal (Inert)</div>
        </div>
      </div>
    </div>
  );
};
