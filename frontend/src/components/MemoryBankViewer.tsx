import React from 'react';
import { Database, Clock } from 'lucide-react';
import { WorkflowMemoryRecord } from '../types/approval';

interface MemoryBankViewerProps {
  workflows: WorkflowMemoryRecord[];
}

export const MemoryBankViewer: React.FC<MemoryBankViewerProps> = ({ workflows }) => {
  const getStateBadge = (state: string) => {
    switch (state) {
      case 'completed':
        return 'bg-emerald-950/80 text-emerald-300 border-emerald-700';
      case 'paused_for_approval':
        return 'bg-amber-950/80 text-amber-300 border-amber-700';
      case 'approved':
        return 'bg-sky-950/80 text-sky-300 border-sky-700';
      case 'failed':
      case 'rejected':
        return 'bg-rose-950/80 text-rose-300 border-rose-700';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-sky-600/30 border border-sky-500/40">
            <Database className="w-5 h-5 text-sky-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white tracking-wide uppercase">Persistent Memory Bank</h2>
            <p className="text-xs text-slate-400">
              Cross-session workflow context, decision logs, and asynchronous state resumption
            </p>
          </div>
        </div>

        <span className="px-2.5 py-1 bg-sky-950/60 border border-sky-800 text-sky-300 text-xs font-mono font-semibold rounded-md flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          {workflows.length} Persistent Workflow{workflows.length === 1 ? '' : 's'}
        </span>
      </div>

      {workflows.length === 0 ? (
        <div className="p-6 text-center bg-slate-950/60 border border-slate-800/80 rounded-xl text-slate-500 text-xs font-mono">
          No workflow records in Memory Bank yet. Run a Critical Demo Case to initialize persistent context.
        </div>
      ) : (
        <div className="space-y-2.5 max-h-64 overflow-y-auto pr-1">
          {workflows.map((wf) => (
            <div
              key={wf.workflow_id}
              className="bg-slate-950 border border-slate-800/80 rounded-lg p-3 text-xs font-mono flex flex-col sm:flex-row sm:items-center justify-between gap-3"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white">{wf.workflow_id}</span>
                  <span className="text-indigo-400">({wf.agent_id})</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold border ${getStateBadge(wf.state)}`}>
                    {wf.state.replace('_', ' ')}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400">
                  Session: <span className="text-slate-300">{wf.session_id}</span> • Policy: <span className="text-amber-400">{wf.policy_version || 'finance-v3'}</span>
                </div>
              </div>

              <div className="text-right text-[11px] text-slate-400">
                {wf.approval_record?.decided_by && (
                  <div className="text-emerald-400 font-semibold">
                    Sign-Off: {wf.approval_record.decided_by}
                  </div>
                )}
                <div className="text-slate-500">
                  Updated: {new Date(wf.updated_at).toLocaleTimeString()}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
