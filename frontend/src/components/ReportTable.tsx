import React from 'react';
import { ExpenseReport } from '../types/approval';
import { Clock, CheckCircle2, AlertCircle, ShieldAlert } from 'lucide-react';

interface ReportTableProps {
  reports: ExpenseReport[];
  onResolve: (id: string) => void;
}

export const ReportTable: React.FC<ReportTableProps> = ({ reports, onResolve }) => {
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Pending':
        return <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-300 border border-amber-800/60"><Clock className="w-3 h-3" /> Pending</span>;
      case 'Nudged':
        return <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-950/80 text-indigo-300 border border-indigo-800/60"><AlertCircle className="w-3 h-3" /> Nudged</span>;
      case 'Escalated':
        return <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-950/80 text-rose-300 border border-rose-800/60"><ShieldAlert className="w-3 h-3" /> Escalated</span>;
      case 'Resolved':
        return <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"><CheckCircle2 className="w-3 h-3" /> Resolved</span>;
      default:
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-300">{status}</span>;
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
      <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          Open Expense Reports
          <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full font-mono">
            {reports.length}
          </span>
        </h2>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
            <tr>
              <th className="py-3 px-4">Report ID</th>
              <th className="py-3 px-4">Submitter</th>
              <th className="py-3 px-4">Amount</th>
              <th className="py-3 px-4">Approver</th>
              <th className="py-3 px-4">Backup</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {reports.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500 italic">
                  No expense reports found. Click "Seed Demo Scenarios" to start.
                </td>
              </tr>
            ) : (
              reports.map((r) => (
                <tr key={r.report_id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-3 px-4 font-mono font-bold text-indigo-300">{r.report_id}</td>
                  <td className="py-3 px-4">
                    <div className="font-semibold text-slate-200">{r.submitter_name}</div>
                    <div className="text-slate-400 text-[11px] truncate max-w-[140px]">{r.description}</div>
                  </td>
                  <td className="py-3 px-4 font-mono font-semibold text-white">
                    {r.currency} {Number(r.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 px-4 text-slate-300 truncate max-w-[140px]">{r.approver_email}</td>
                  <td className="py-3 px-4 text-slate-400 truncate max-w-[130px]">
                    {r.backup_approver_email || <span className="italic text-slate-600">Admin Fallback</span>}
                  </td>
                  <td className="py-3 px-4">{getStatusBadge(r.status)}</td>
                  <td className="py-3 px-4 text-right">
                    {r.status !== 'Resolved' ? (
                      <button
                        onClick={() => onResolve(r.report_id)}
                        className="px-2.5 py-1 bg-slate-800 hover:bg-emerald-700 text-slate-200 hover:text-white rounded text-[11px] font-semibold transition-colors border border-slate-700"
                      >
                        Sign Off
                      </button>
                    ) : (
                      <span className="text-slate-600 text-[11px]">Completed</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
