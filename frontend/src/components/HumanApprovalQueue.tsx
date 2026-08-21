import React, { useState } from 'react';
import { UserCheck, CheckCircle2, XCircle, Clock, ShieldAlert } from 'lucide-react';
import { PendingAction } from '../types/approval';

interface HumanApprovalQueueProps {
  pendingActions: PendingAction[];
  onApprove: (actionId: string, operator: string, notes: string) => Promise<void>;
  onReject: (actionId: string, operator: string, notes: string) => Promise<void>;
}

export const HumanApprovalQueue: React.FC<HumanApprovalQueueProps> = ({
  pendingActions,
  onApprove,
  onReject,
}) => {
  const [operator, setOperator] = useState('Chief Risk Officer');
  const [notes, setNotes] = useState('Approved after financial policy inspection');
  const [processingId, setProcessingId] = useState<string | null>(null);

  const handleApprove = async (actionId: string) => {
    setProcessingId(actionId);
    try {
      await onApprove(actionId, operator, notes);
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (actionId: string) => {
    setProcessingId(actionId);
    try {
      await onReject(actionId, operator, notes);
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-amber-600/30 border border-amber-500/40">
            <UserCheck className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white tracking-wide uppercase">Human-in-the-Loop Approval Queue</h2>
            <p className="text-xs text-slate-400">
              Consequential actions paused by Gateway Policy requiring authoritative human sign-off
            </p>
          </div>
        </div>

        <span className="px-2.5 py-1 bg-amber-950/60 border border-amber-800 text-amber-300 text-xs font-mono font-semibold rounded-md flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          {pendingActions.length} Pending Sign-Off{pendingActions.length === 1 ? '' : 's'}
        </span>
      </div>

      {pendingActions.length === 0 ? (
        <div className="p-8 text-center bg-slate-950/60 border border-slate-800/80 rounded-xl">
          <ShieldAlert className="w-8 h-8 text-slate-600 mx-auto mb-2" />
          <p className="text-sm text-slate-400 font-semibold">No Pending Approvals</p>
          <p className="text-xs text-slate-500 mt-1">
            All low-risk actions were automatically authorized or executed. Trigger <b>Case B (Refund ₹20,000)</b> to test the human approval workflow.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {pendingActions.map((item) => (
            <div
              key={item.action_id}
              className="bg-slate-950 border border-amber-800/60 rounded-xl p-4 space-y-3 shadow-lg"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded bg-amber-950 border border-amber-700 text-amber-300 text-xs font-mono font-bold uppercase">
                    Requires Human Sign-Off
                  </span>
                  <span className="text-xs font-mono text-slate-400">
                    Action ID: <b className="text-slate-200">{item.action_id}</b>
                  </span>
                </div>
                <span className="text-xs font-mono text-slate-400">
                  Agent: <b className="text-indigo-400">{item.proposal.agent_id}</b>
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800">
                  <span className="text-slate-400 block mb-1">Proposed Action:</span>
                  <span className="font-bold text-white text-sm">{item.proposal.action_name}</span>
                </div>
                <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800">
                  <span className="text-slate-400 block mb-1">Target Resource / Amount:</span>
                  <span className="font-bold text-emerald-400 text-sm">
                    {item.proposal.target_resource_id} {item.proposal.amount ? `(${item.proposal.currency} ${item.proposal.amount})` : ''}
                  </span>
                </div>
                <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800">
                  <span className="text-slate-400 block mb-1">Policy Reason:</span>
                  <span className="font-semibold text-amber-300 line-clamp-2">
                    {item.decision.reason}
                  </span>
                </div>
              </div>

              <div className="bg-slate-900/50 p-2.5 rounded-lg border border-slate-800/60 text-xs text-slate-300">
                <span className="text-slate-400 font-semibold">Agent Justification:</span> {item.proposal.justification}
              </div>

              {/* Operator Inputs */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs pt-1">
                <div>
                  <label className="text-slate-400 text-[11px] block mb-1">Approving Operator:</label>
                  <input
                    type="text"
                    value={operator}
                    onChange={(e) => setOperator(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-slate-400 text-[11px] block mb-1">Audit Notes:</label>
                  <input
                    type="text"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="flex flex-col sm:flex-row items-center justify-end gap-2 pt-2 border-t border-slate-800/80">
                <button
                  disabled={processingId === item.action_id}
                  onClick={() => handleReject(item.action_id)}
                  className="w-full sm:w-auto px-4 py-2 bg-rose-950/80 hover:bg-rose-900 text-rose-200 border border-rose-800 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                >
                  <XCircle className="w-4 h-4 text-rose-400" />
                  Reject &amp; Terminate
                </button>

                <button
                  disabled={processingId === item.action_id}
                  onClick={() => handleApprove(item.action_id)}
                  className="w-full sm:w-auto px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold shadow-lg shadow-emerald-600/30 flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Authorize &amp; Execute
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
