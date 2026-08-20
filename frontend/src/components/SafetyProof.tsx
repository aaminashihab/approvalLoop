import React from 'react';
import { ShieldCheck, CheckCircle, Lock } from 'lucide-react';

export const SafetyProof: React.FC = () => {
  const proofs = [
    {
      title: "Deterministic Recipient Gate",
      desc: "ApproverRegistry hierarchy check blocks unauthorized or hallucinated recipients.",
      icon: <CheckCircle className="w-4 h-4 text-emerald-400" />
    },
    {
      title: "Exact Monetary Precision",
      desc: "Python Decimal arithmetic prevents floating-point drift and amount alterations.",
      icon: <CheckCircle className="w-4 h-4 text-emerald-400" />
    },
    {
      title: "State Machine Invariants",
      desc: "Strict legal transitions (Pending → Nudged → Escalated → Resolved). Reverts blocked.",
      icon: <CheckCircle className="w-4 h-4 text-emerald-400" />
    },
    {
      title: "Corporate Policy Engine",
      desc: "Enforces domain restrictions, director limits (≥ $5,000), and environment guards.",
      icon: <CheckCircle className="w-4 h-4 text-emerald-400" />
    },
    {
      title: "Transactional Outbox Claim",
      desc: "Atomic claim on {report_id}:{action_type} before LLM invocation prevents duplicate sends.",
      icon: <CheckCircle className="w-4 h-4 text-emerald-400" />
    },
    {
      title: "Scenario 13 Race Guard",
      desc: "Verifies current_state == source_state before commit. Preserves human sign-offs mid-flight.",
      icon: <CheckCircle className="w-4 h-4 text-emerald-400" />
    },
    {
      title: "Bounded Retry & Backoff",
      desc: "Exponential backoff on upstream provider timeouts prevents infinite loops and storms.",
      icon: <CheckCircle className="w-4 h-4 text-emerald-400" />
    },
    {
      title: "OpenTelemetry Execution Trace",
      desc: "End-to-end span tracking with sanitized credentials for 100% auditable execution.",
      icon: <CheckCircle className="w-4 h-4 text-emerald-400" />
    }
  ];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl relative overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 bg-emerald-500/20 text-emerald-400 rounded-lg border border-emerald-500/30">
              <ShieldCheck className="w-5 h-5" />
            </span>
            <h2 className="text-sm font-black tracking-wider text-white uppercase">
              Control Plane &amp; Deterministic Safety Invariants
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Core Thesis: <span className="text-indigo-300 font-semibold italic">“The LLM writes the message. Code controls the consequences.”</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1 bg-emerald-950/80 border border-emerald-500/30 text-emerald-300 text-[11px] font-mono font-bold rounded-lg flex items-center gap-1.5">
            <Lock className="w-3 h-3 text-emerald-400" /> 8/8 Active Invariants
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-4 text-xs">
        {proofs.map((p, idx) => (
          <div key={idx} className="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80 hover:border-slate-700 transition-colors">
            <div className="flex items-center gap-2 font-bold text-white mb-1">
              {p.icon}
              <span>{p.title}</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              {p.desc}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};
