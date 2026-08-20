import React from 'react';
import { Play, FastForward, ShieldAlert, Sparkles, RefreshCw, Skull, Radio, AlertTriangle, RotateCcw } from 'lucide-react';

interface ScenarioRunnerProps {
  onTick: () => void;
  onSeed: () => void;
  onAdvanceTime: () => void;
  onSimulateRace: () => void;
  onSimulateAdversarial: () => void;
  onSimulateNotificationFailure: () => void;
  onResetDemo: () => void;
  isLiveMode: boolean;
  onToggleLiveMode: () => void;
}

export const ScenarioRunner: React.FC<ScenarioRunnerProps> = ({
  onTick,
  onSeed,
  onAdvanceTime,
  onSimulateRace,
  onSimulateAdversarial,
  onSimulateNotificationFailure,
  onResetDemo,
  isLiveMode,
  onToggleLiveMode
}) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          Autonomous Controls &amp; Live Judging Testbeds
        </h3>

        {/* Live Mode Toggle Button */}
        <button
          onClick={onToggleLiveMode}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold transition-all ${
            isLiveMode
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
              : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
          }`}
        >
          <Radio className={`w-3.5 h-3.5 ${isLiveMode ? 'animate-pulse text-emerald-300' : ''}`} />
          {isLiveMode ? 'Judging / Live Autonomous Mode (Active)' : 'Switch to Judging Mode'}
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-2 text-xs">
        <button
          onClick={onSeed}
          className="flex items-center justify-center gap-1.5 py-2.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg font-semibold border border-slate-700 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5 text-sky-400" />
          Seed Data
        </button>

        <button
          onClick={onTick}
          className="flex items-center justify-center gap-1.5 py-2.5 px-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-semibold shadow-md transition-colors"
        >
          <Play className="w-3.5 h-3.5 fill-current" />
          Trigger Tick
        </button>

        <button
          onClick={onAdvanceTime}
          className="flex items-center justify-center gap-1.5 py-2.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg font-semibold border border-slate-700 transition-colors"
        >
          <FastForward className="w-3.5 h-3.5 text-amber-400" />
          Advance (+35s)
        </button>

        <button
          onClick={onSimulateAdversarial}
          className="flex items-center justify-center gap-1.5 py-2.5 px-3 bg-rose-950/60 hover:bg-rose-900/80 text-rose-200 rounded-lg font-semibold border border-rose-800 transition-colors"
        >
          <Skull className="w-3.5 h-3.5 text-rose-400" />
          Adversarial Test
        </button>

        <button
          onClick={onSimulateRace}
          className="flex items-center justify-center gap-1.5 py-2.5 px-3 bg-amber-950/60 hover:bg-amber-900/80 text-amber-200 rounded-lg font-semibold border border-amber-800 transition-colors"
        >
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
          Race Condition
        </button>

        <button
          onClick={onSimulateNotificationFailure}
          className="flex items-center justify-center gap-1.5 py-2.5 px-3 bg-purple-950/60 hover:bg-purple-900/80 text-purple-200 rounded-lg font-semibold border border-purple-800 transition-colors"
        >
          <AlertTriangle className="w-3.5 h-3.5 text-purple-400" />
          Retry / Timeout
        </button>

        <button
          onClick={onResetDemo}
          className="flex items-center justify-center gap-1.5 py-2.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 rounded-lg font-semibold border border-slate-700 transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
          Reset State
        </button>
      </div>
    </div>
  );
};

