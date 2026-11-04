import { useMemo, useState } from 'react';
import { api, errorMessage } from '../api/client';
import { Button, Chip, Empty, LoadFailed, Loading, Notice, SectionHeader, Tone, ViewHeader } from '../components/ui';
import { ago, formatMoney, humanize } from '../lib/format';
import type { Source } from '../lib/useConsoleData';
import type { ActionRecord, ExpenseReport } from '../types/approval';

const REPORT_TONE: Record<ExpenseReport['status'], Tone> = { Pending: 'neutral', Nudged: 'review', Escalated: 'block', Resolved: 'auto' };
const REMINDER_TONE: Record<ActionRecord['status'], Tone> = {
  claimed: 'neutral', processing: 'neutral', sent: 'auto', completed: 'auto', failed: 'block', blocked: 'block',
};
const REMINDERS_SHOWN = 25;

interface Props {
  reports: Source<ExpenseReport[]>;
  actions: Source<ActionRecord[]>;
  refresh: () => Promise<void>;
}

export function ExpensesView({ reports, actions, refresh }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [note, setNote] = useState<{ tone: 'ok' | 'error'; title: string; body?: string } | null>(null);

  const openFirst = useMemo(
    () => [...(reports.data ?? [])].sort((a, b) =>
      Number(a.status === 'Resolved') - Number(b.status === 'Resolved') || Date.parse(a.submitted_at) - Date.parse(b.submitted_at)),
    [reports.data],
  );
  const recent = useMemo(
    () => [...(actions.data ?? [])].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, REMINDERS_SHOWN),
    [actions.data],
  );
  const openCount = openFirst.filter((r) => r.status !== 'Resolved').length;

  const resolve = async (r: ExpenseReport) => {
    setBusyId(r.report_id);
    setNote(null);
    try {
      await api.resolveReport(r.report_id);
      setNote({ tone: 'ok', title: `${r.report_id} marked resolved. No further reminders will be sent for it.` });
      await refresh();
    } catch (e) {
      setNote({ tone: 'error', title: `${r.report_id} was not marked resolved.`, body: errorMessage(e) });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section aria-labelledby="expenses-title">
      <ViewHeader
        id="expenses-title"
        title="Expenses"
        lede="Expense reports waiting on an approver. The system reminds the approver first, then escalates to their backup."
        sources={[reports, actions]}
      />

      {note && <div className="mt-6"><Notice tone={note.tone} title={note.title}>{note.body}</Notice></div>}

      <section aria-labelledby="reports-title" className="mt-8">
        <SectionHeader id="reports-title" title="Waiting on approvers" aside={reports.data ? `${openCount} open` : undefined} />
        {reports.data === null ? (
          reports.error ? <LoadFailed what="expense reports" error={reports.error} /> : <Loading what="expense reports" />
        ) : openFirst.length === 0 ? (
          <Empty title="No expense reports." hint="Reports submitted for approval appear here with who they are waiting on and for how long." />
        ) : (
          <ul className="m-0 list-none border-t border-rule p-0">
            {openFirst.map((r) => (
              <li key={r.report_id} className="grid gap-x-6 gap-y-2 border-b border-rule py-4 sm:grid-cols-[minmax(0,1fr)_auto_9.5rem] sm:items-center">
                <div className="min-w-0">
                  <p className="break-words text-sm font-medium">{r.description}</p>
                  <p className="text-xs text-ink-mute">
                    {r.report_id} · {r.submitter_name} · waiting on {r.approver_email} · submitted {ago(r.submitted_at)}
                  </p>
                </div>
                <div className="flex items-center gap-3 sm:justify-end">
                  <span className="font-serif text-xl">{formatMoney(r.amount, r.currency)}</span>
                  <Chip tone={REPORT_TONE[r.status] ?? 'neutral'}>{r.status}</Chip>
                </div>
                {r.status !== 'Resolved' ? (
                  <Button disabled={busyId !== null} onClick={() => void resolve(r)} aria-label={`Mark ${r.report_id} resolved`}>
                    {busyId === r.report_id ? 'Saving…' : 'Mark resolved'}
                  </Button>
                ) : (
                  <span className="hidden sm:block" />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="reminders-title" className="mt-10">
        <SectionHeader id="reminders-title" title="Latest reminders" aside={actions.data && actions.data.length > REMINDERS_SHOWN ? `latest ${REMINDERS_SHOWN} of ${actions.data.length}` : undefined} />
        {actions.data === null ? (
          actions.error ? <LoadFailed what="the reminder log" error={actions.error} /> : <Loading what="the reminder log" />
        ) : recent.length === 0 ? (
          <Empty title="No reminders sent yet." hint="Each reminder or escalation appears here with its delivery status, retry attempts and any error." />
        ) : (
          <ul className="m-0 list-none border-t border-rule p-0">
            {recent.map((a) => (
              <li key={a.action_id} className="border-b border-rule py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <p className="min-w-0 break-words text-sm">
                    <span className="font-medium">{humanize(a.action_type)}</span> for {a.report_id} to {a.recipient}
                  </p>
                  <Chip tone={REMINDER_TONE[a.status] ?? 'neutral'}>{humanize(a.status)}</Chip>
                </div>
                <p className="text-xs text-ink-mute">
                  {ago(a.created_at)} · attempt {a.attempt_count} of {a.max_attempts}
                </p>
                {a.last_error && <p className="mt-1 break-words text-sm text-block">Error: {a.last_error}</p>}
                {a.validator_result === 'blocked' && a.validator_reason && (
                  <p className="mt-1 break-words text-sm text-block">Blocked by validator: {a.validator_reason}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
