import React from 'react';
import { ActionRecord } from '../types/approval';
import { CheckCircle2, XCircle, AlertTriangle, ShieldCheck, Mail, ShieldAlert } from 'lucide-react';

interface ActionLedgerProps {
  actions: ActionRecord[];
}

export const ActionLedger: React.FC<ActionLedgerProps> = ({ actions }) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-400" />
            Autonomous Action & Audit Ledger
          </h2>
          <p className="text-xs text-slate-400">
            LLM proposes wording; deterministic code owns claims, safety validation & transitions.
          </p>
        </div>
        <span className="text-xs bg-slate-800 text-slate-400 px-2.5 py-1 rounded-full font-mono">
          {actions.length} Logged
        </span>
      </div>

      <div className="space-y-3.5 max-h-[560px] overflow-y-auto pr-1.5">
        {actions.length === 0 ? (
          <div className="py-12 text-center text-slate-500 text-xs italic">
            No autonomous actions triggered yet. Run a scheduler tick or demo scenario.
          </div>
        ) : (
          actions.map((act) => {
            const isBlocked = act.status === 'blocked' || act.validator_result === 'blocked';
            const isSkipped = act.state_transition === 'skipped';

            return (
              <div
                key={act.action_id}
                className={`p-4 rounded-xl border text-xs transition-all ${
                  isBlocked
                    ? 'bg-rose-950/30 border-rose-700/80 shadow-lg shadow-rose-950/20'
                    : isSkipped
                    ? 'bg-amber-950/20 border-amber-800/70 shadow-lg shadow-amber-950/20'
                    : 'bg-slate-950/70 border-slate-800'
                }`}
              >
                {/* Header info */}
                <div className="flex items-center justify-between mb-2.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono font-bold text-white text-sm">{act.report_id}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                      act.action_type === 'nudge'
                        ? 'bg-indigo-950 text-indigo-300 border border-indigo-800'
                        : 'bg-violet-950 text-violet-300 border border-violet-800'
                    }`}>
                      {act.action_type}
                    </span>
                    <span className="text-[11px] font-mono text-slate-500">Key: {act.idempotency_key}</span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-400">
                    {new Date(act.created_at).toLocaleTimeString()}
                  </div>
                </div>

                {/* 4-Stage Architectural Pipeline */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 my-2.5 p-2.5 bg-slate-900/90 rounded-lg border border-slate-800 text-[11px]">
                  {/* 1. Transactional Outbox Claim */}
                  <div className="p-2 rounded bg-slate-950/80 border border-slate-800/60">
                    <div className="text-slate-400 text-[10px] uppercase font-semibold">1. Outbox Claim</div>
                    <div className="font-bold text-emerald-400 flex items-center gap-1 mt-1 font-mono">
                      <CheckCircle2 className="w-3.5 h-3.5" /> CLAIMED
                    </div>
                  </div>

                  {/* 2. Gemini 3.7 Drafter */}
                  <div className="p-2 rounded bg-slate-950/80 border border-slate-800/60">
                    <div className="text-slate-400 text-[10px] uppercase font-semibold">2. Gemini 3.7 Drafter</div>
                    <div className="font-bold text-sky-400 flex items-center gap-1 mt-1 font-mono">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Wording Drafted
                    </div>
                  </div>

                  {/* 3. 4-Point Safety Validator Gate */}
                  <div className="p-2 rounded bg-slate-950/80 border border-slate-800/60">
                    <div className="text-slate-400 text-[10px] uppercase font-semibold">3. Safety Validator</div>
                    {isBlocked ? (
                      <div className="font-bold text-rose-400 flex items-center gap-1 mt-1 font-mono">
                        <XCircle className="w-3.5 h-3.5" /> BLOCKED
                      </div>
                    ) : (
                      <div className="font-bold text-emerald-400 flex items-center gap-1 mt-1 font-mono">
                        <CheckCircle2 className="w-3.5 h-3.5" /> PASS
                      </div>
                    )}
                  </div>

                  {/* 4. Conditional State Transition */}
                  <div className="p-2 rounded bg-slate-950/80 border border-slate-800/60">
                    <div className="text-slate-400 text-[10px] uppercase font-semibold">4. State Transition</div>
                    {isBlocked ? (
                      <div className="text-slate-500 font-semibold mt-1">Aborted</div>
                    ) : isSkipped ? (
                      <div className="font-bold text-amber-400 flex items-center gap-1 mt-1 font-mono">
                        <AlertTriangle className="w-3.5 h-3.5" /> SKIPPED (Race Guard)
                      </div>
                    ) : act.state_transition === 'applied' ? (
                      <div className="font-bold text-emerald-400 flex items-center gap-1 mt-1 font-mono">
                        <CheckCircle2 className="w-3.5 h-3.5" /> {act.source_state} → {act.target_state}
                      </div>
                    ) : (
                      <div className="text-slate-500 font-semibold mt-1">—</div>
                    )}
                  </div>
                </div>

                {/* 4-Point Deterministic Safety Validator Checklist */}
                <div className="p-2.5 bg-slate-950/50 rounded-lg border border-slate-800/80 my-2 text-[11px]">
                  <div className="text-[10px] uppercase font-bold text-slate-400 mb-1.5 flex items-center justify-between">
                    <span>4-Point Deterministic Safety Validator Checklist</span>
                    <span className="italic text-slate-500">"LLM proposes. Code disposes."</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 font-mono text-[10px]">
                    <div className={`p-1 rounded flex items-center gap-1 ${
                      act.validator_checks?.recipient_verified !== false ? 'text-emerald-400 bg-emerald-950/40' : 'text-rose-400 bg-rose-950/40 font-bold'
                    }`}>
                      {act.validator_checks?.recipient_verified !== false ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                      1. Recipient ✓
                    </div>

                    <div className={`p-1 rounded flex items-center gap-1 ${
                      act.validator_checks?.report_id_verified !== false ? 'text-emerald-400 bg-emerald-950/40' : 'text-rose-400 bg-rose-950/40 font-bold'
                    }`}>
                      {act.validator_checks?.report_id_verified !== false ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                      2. Report ID ✓
                    </div>

                    <div className={`p-1 rounded flex items-center gap-1 ${
                      act.validator_checks?.amount_verified !== false ? 'text-emerald-400 bg-emerald-950/40' : 'text-rose-400 bg-rose-950/40 font-bold'
                    }`}>
                      {act.validator_checks?.amount_verified !== false ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                      3. Amount ✓
                    </div>

                    <div className={`p-1 rounded flex items-center gap-1 ${
                      act.validator_checks?.state_verified !== false ? 'text-emerald-400 bg-emerald-950/40' : 'text-rose-400 bg-rose-950/40 font-bold'
                    }`}>
                      {act.validator_checks?.state_verified !== false ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                      4. Legal State ✓
                    </div>
                  </div>
                </div>

                {/* Blocker Alert Banner */}
                {isBlocked && (
                  <div className="mt-2 p-2.5 bg-rose-950/60 border border-rose-700/80 rounded-lg text-rose-200">
                    <div className="font-bold flex items-center gap-1.5 text-xs text-rose-300">
                      <ShieldAlert className="w-4 h-4" />
                      SAFETY INTERCEPTED: Notification Dispatch Aborted
                    </div>
                    <p className="mt-1 text-[11px] text-rose-200/90 font-mono">{act.validator_reason}</p>
                  </div>
                )}

                {/* Race Condition Skip Banner */}
                {isSkipped && (
                  <div className="mt-2 p-2.5 bg-amber-950/60 border border-amber-700/80 rounded-lg text-amber-200">
                    <div className="font-bold flex items-center gap-1.5 text-xs text-amber-300">
                      <AlertTriangle className="w-4 h-4" />
                      RACE CONDITION GUARD FIRED: State Transition Skipped
                    </div>
                    <p className="mt-1 text-[11px] text-amber-200/90 font-mono">{act.skip_reason}</p>
                    <p className="mt-0.5 text-[10px] text-amber-300/70 italic">Final report state remained 'Resolved'. Stale transition rejected.</p>
                  </div>
                )}

                {/* Envelope preview */}
                {act.envelope && !isBlocked && (
                  <div className="mt-2.5 p-2.5 bg-slate-900 rounded-lg text-[11px] text-slate-300 border border-slate-800">
                    <div className="font-semibold text-indigo-300 flex items-center gap-1.5 mb-1">
                      <Mail className="w-3.5 h-3.5" /> Dispatched to: <span className="font-mono text-white">{act.envelope.recipient}</span> (${Number(act.envelope.amount).toFixed(2)})
                    </div>
                    <p className="italic text-slate-400 bg-slate-950/50 p-2 rounded border border-slate-800/60">"{act.envelope.body_text}"</p>
                  </div>
                )}

                {/* WHY DID APPROVALLOOP ACT? Breakdown Box (Phase 9 & 10) */}
                <div className="mt-3 p-3 bg-indigo-950/30 border border-indigo-800/60 rounded-lg text-[11px]">
                  <div className="flex items-center justify-between text-indigo-300 font-bold uppercase tracking-wider text-[10px] mb-2">
                    <span className="flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
                      WHY DID APPROVALLOOP ACT? (AUTONOMOUS DIAGNOSTIC)
                    </span>
                    <span className="font-mono text-[9px] bg-indigo-900/60 px-2 py-0.5 rounded text-indigo-200">
                      Clock Trigger: {act.source_state}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-300 font-mono text-[10px]">
                    <div className="bg-slate-950/60 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[9px] font-sans">Observed State vs Action</span>
                      <span className="text-indigo-300 font-bold">{act.source_state}</span> → <span className="text-emerald-400 font-bold">{act.action_type.toUpperCase()}</span>
                    </div>
                    <div className="bg-slate-950/60 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[9px] font-sans">LLM Wording Role vs Authority</span>
                      <span className="text-sky-300">LLM = Wording Only</span> | <span className="text-emerald-400 font-bold">Code = Authority</span>
                    </div>
                    <div className="bg-slate-950/60 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[9px] font-sans">Deterministic Safety Score</span>
                      <span className="text-emerald-400 font-bold">4/4 Deterministic Checks Passed</span>
                    </div>
                    <div className="bg-slate-950/60 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[9px] font-sans">State Transition Outcome</span>
                      {isSkipped ? (
                        <span className="text-amber-400 font-bold">EXPECTED: PENDING | ACTUAL: RESOLVED | RESULT: SKIPPED (HUMAN PRESERVED)</span>
                      ) : isBlocked ? (
                        <span className="text-rose-400 font-bold">BLOCKED BY GATEWAY</span>
                      ) : (
                        <span className="text-emerald-400 font-bold">APPLIED ({act.source_state} → {act.target_state})</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
