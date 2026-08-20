import React from 'react';
import { AutonomyMetrics } from '../types/approval';
import { Zap, Bot } from 'lucide-react';

interface AutonomyProofProps {
  metrics: AutonomyMetrics;
  isLiveMode: boolean;
}

export const AutonomyProof: React.FC<AutonomyProofProps> = ({ metrics, isLiveMode }) => {
  return (
    <div className="bg-gradient-to-br from-slate-900 via-indigo-950/30 to-slate-900 border border-indigo-900/60 rounded-2xl p-6 shadow-2xl relative overflow-hidden">
      {/* Background glow accent */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none" />

      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-5 border-b border-slate-800/80">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="p-1.5 bg-indigo-500/20 text-indigo-400 rounded-lg border border-indigo-500/30">
              <Zap className="w-5 h-5" />
            </span>
            <h2 className="text-lg font-black tracking-wide text-white uppercase">
              Autonomy Proof & Safety Invariants
            </h2>
          </div>
          <p className="text-xs text-indigo-200/70 mt-1">
            "Most agents wait for a prompt. ApprovalLoop acts when nothing happens."
          </p>
        </div>

        {/* Human Prompts Required for Autonomous Loop: 0 */}
        <div className="flex items-center gap-3">
          <div className="px-4 py-2 bg-emerald-950/80 border border-emerald-500/40 rounded-xl flex items-center gap-2.5 shadow-lg shadow-emerald-950/40">
            <Bot className="w-5 h-5 text-emerald-400 animate-pulse" />
            <div>
              <div className="text-[10px] uppercase font-bold text-emerald-300/80 tracking-wider">
                Human Prompts Required for Autonomous Loop
              </div>
              <div className="text-lg font-black text-emerald-400 font-mono leading-none">
                0
              </div>
            </div>
          </div>

          <div className={`px-3 py-2 rounded-xl text-xs font-mono border flex items-center gap-2 ${
            isLiveMode
              ? 'bg-indigo-950/80 text-indigo-300 border-indigo-700'
              : 'bg-slate-800/80 text-slate-300 border-slate-700'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isLiveMode ? 'bg-emerald-400 animate-ping' : 'bg-amber-400'}`} />
            {isLiveMode ? 'Autonomous Trigger: Active' : 'Manual Testing Mode'}
          </div>
        </div>
      </div>

      {/* Autonomous Loop Visual Flow */}
      <div className="my-5 p-3.5 bg-slate-950/70 rounded-xl border border-slate-800 text-xs">
        <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 mb-2 flex items-center justify-between">
          <span>Autonomous Loop Pipeline</span>
          <span className="text-indigo-400 font-mono">Cloud Scheduler Triggered Backend Execution</span>
        </div>
        <div className="grid grid-cols-5 gap-2 text-center font-mono">
          <div className="p-2 bg-slate-900 rounded border border-slate-800 text-slate-300 flex flex-col items-center justify-center">
            <span className="text-indigo-400 font-bold text-[11px]">1. OBSERVE</span>
            <span className="text-[10px] text-slate-500">Scan Open Approvals</span>
          </div>
          <div className="p-2 bg-slate-900 rounded border border-slate-800 text-slate-300 flex flex-col items-center justify-center">
            <span className="text-sky-400 font-bold text-[11px]">2. DECIDE</span>
            <span className="text-[10px] text-slate-500">Time Thresholds</span>
          </div>
          <div className="p-2 bg-slate-900 rounded border border-slate-800 text-slate-300 flex flex-col items-center justify-center">
            <span className="text-violet-400 font-bold text-[11px]">3. DRAFT</span>
            <span className="text-[10px] text-slate-500">Gemini 3.5 Flash</span>
          </div>
          <div className="p-2 bg-slate-900 rounded border border-slate-800 text-slate-300 flex flex-col items-center justify-center">
            <span className="text-emerald-400 font-bold text-[11px]">4. VERIFY</span>
            <span className="text-[10px] text-slate-500">4-Point Safety & Policy</span>
          </div>
          <div className="p-2 bg-slate-900 rounded border border-slate-800 text-slate-300 flex flex-col items-center justify-center">
            <span className="text-amber-400 font-bold text-[11px]">5. REPEAT</span>
            <span className="text-[10px] text-slate-500">Sleep Until Next Cron</span>
          </div>
        </div>
      </div>

      {/* Live Invariant Proof Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 text-xs">
        <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
          <div className="text-[10px] text-slate-400 uppercase font-semibold">Observed</div>
          <div className="text-lg font-bold text-white font-mono mt-0.5">{metrics.reports_observed}</div>
          <div className="text-[10px] text-slate-500">Reports Scanned</div>
        </div>

        <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
          <div className="text-[10px] text-indigo-300 uppercase font-semibold">Eligible</div>
          <div className="text-lg font-bold text-indigo-400 font-mono mt-0.5">{metrics.eligible_reports}</div>
          <div className="text-[10px] text-slate-500">Exceeded Clock</div>
        </div>

        <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
          <div className="text-[10px] text-sky-300 uppercase font-semibold">Claimed</div>
          <div className="text-lg font-bold text-sky-400 font-mono mt-0.5">{metrics.actions_claimed}</div>
          <div className="text-[10px] text-slate-500">Atomic Outbox</div>
        </div>

        <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
          <div className="text-[10px] text-emerald-300 uppercase font-semibold">Sent</div>
          <div className="text-lg font-bold text-emerald-400 font-mono mt-0.5">{metrics.notifications_sent}</div>
          <div className="text-[10px] text-slate-500">Notifications</div>
        </div>

        <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
          <div className="text-[10px] text-violet-300 uppercase font-semibold">Escalations</div>
          <div className="text-lg font-bold text-violet-400 font-mono mt-0.5">{metrics.escalations_count}</div>
          <div className="text-[10px] text-slate-500">To Backups/Admin</div>
        </div>

        <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
          <div className="text-[10px] text-rose-300 uppercase font-semibold">Blocked</div>
          <div className="text-lg font-bold text-rose-400 font-mono mt-0.5">{metrics.blocked_actions_count}</div>
          <div className="text-[10px] text-slate-500">Safety Rejections</div>
        </div>

        <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
          <div className="text-[10px] text-teal-300 uppercase font-semibold">Dedup Prev.</div>
          <div className="text-lg font-bold text-teal-400 font-mono mt-0.5">{metrics.duplicate_actions_prevented}</div>
          <div className="text-[10px] text-slate-500">0 Duplicate Sends</div>
        </div>

        <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
          <div className="text-[10px] text-amber-300 uppercase font-semibold">Race Guard</div>
          <div className="text-lg font-bold text-amber-400 font-mono mt-0.5">{metrics.unsafe_transitions_prevented}</div>
          <div className="text-[10px] text-slate-500">Skips on Mid-Flight</div>
        </div>
      </div>
    </div>
  );
};
