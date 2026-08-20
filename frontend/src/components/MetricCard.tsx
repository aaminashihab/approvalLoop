import React from 'react';
import { LucideIcon } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle: string;
  icon: LucideIcon;
  color: 'indigo' | 'emerald' | 'amber' | 'rose';
}

export const MetricCard: React.FC<MetricCardProps> = ({ title, value, subtitle, icon: Icon, color }) => {
  const colorMap = {
    indigo: 'bg-indigo-950/40 border-indigo-800/40 text-indigo-400',
    emerald: 'bg-emerald-950/40 border-emerald-800/40 text-emerald-400',
    amber: 'bg-amber-950/40 border-amber-800/40 text-amber-400',
    rose: 'bg-rose-950/40 border-rose-800/40 text-rose-400',
  };

  return (
    <div className={`p-4 rounded-xl border ${colorMap[color]} shadow-lg flex items-center justify-between`}>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</p>
        <p className="text-2xl font-bold text-white mt-1">{value}</p>
        <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>
      </div>
      <div className={`p-3 rounded-lg bg-slate-900/60 border border-slate-800`}>
        <Icon className="w-6 h-6" />
      </div>
    </div>
  );
};
