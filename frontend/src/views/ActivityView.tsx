import { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Chip, Empty, LoadFailed, Loading, SectionHeader, Tone, ViewHeader } from '../components/ui';
import { ago, dateTime, formatMoney, humanize } from '../lib/format';
import type { Source } from '../lib/useConsoleData';
import type { ActionProposal, AutonomyMetrics, GatewayDecision, WorkflowMemoryRecord } from '../types/approval';

const STATE: Record<WorkflowMemoryRecord['state'], { label: string; tone: Tone }> = {
  initialized: { label: 'Started', tone: 'neutral' },
  running: { label: 'Running', tone: 'neutral' },
  paused_for_approval: { label: 'Waiting for a person', tone: 'review' },
  approved: { label: 'Approved', tone: 'auto' },
  rejected: { label: 'Rejected', tone: 'block' },
  completed: { label: 'Completed', tone: 'auto' },
  failed: { label: 'Execution failed', tone: 'block' },
  denied: { label: 'Blocked', tone: 'block' },
};

const DECISION: Record<GatewayDecision['decision'], { label: string; tone: Tone }> = {
  allow: { label: 'Allowed', tone: 'auto' },
  require_human_approval: { label: 'Needs a person', tone: 'review' },
  deny: { label: 'Blocked', tone: 'block' },
};

const REVIEW_TONE: Record<string, Tone> = { pending: 'review', approved: 'auto', rejected: 'block', expired: 'block' };

function proposalSummary(p: ActionProposal | undefined): string {
  if (!p) return 'Unknown action';
  const amount = p.amount ? `, ${formatMoney(p.amount, p.currency)}` : p.parameters?.discount_percent !== undefined ? `, ${p.parameters.discount_percent}% discount` : '';
  return `${humanize(p.action_name)}${amount}`;
}

function Figure({ value, label, note }: { value: number | null; label: string; note: string }) {
  return (
    <div className="py-4 pr-4 sm:py-0 sm:pl-6 sm:first:pl-0">
      <dt className="text-sm text-ink-soft">{label}</dt>
      <dd className="m-0 font-serif text-4xl leading-tight">{value ?? '–'}</dd>
      <dd className="m-0 text-xs text-ink-mute">{note}</dd>
    </div>
  );
}

/** Workflows recorded before the "denied" state existed were stored as "failed"; still label those as blocked. */
function stateOf(wf: WorkflowMemoryRecord): { label: string; tone: Tone } {
  const last = wf.previous_decisions[wf.previous_decisions.length - 1];
  if (wf.state === 'failed' && last?.decision === 'deny' && wf.tool_results.length === 0) return { label: 'Blocked', tone: 'block' };
  return STATE[wf.state] ?? { label: humanize(wf.state), tone: 'neutral' };
}

function WorkflowRow({ wf }: { wf: WorkflowMemoryRecord }) {
  const [open, setOpen] = useState(false);
  const state = stateOf(wf);
  const latest = wf.action_history[wf.action_history.length - 1];
  const panelId = `wf-${wf.workflow_id}`;
  const review = wf.approval_record;

  return (
    <li className="border-b border-rule">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        className="grid min-h-touch w-full grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-x-3 py-3 text-left hover:bg-sheet/60"
      >
        <ChevronDown className={`h-4 w-4 text-ink-mute ${open ? '' : '-rotate-90'}`} aria-hidden="true" />
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">
            {proposalSummary(latest)}{latest && <span className="font-normal text-ink-soft"> · {latest.target_resource_id}</span>}
          </span>
          <span className="block truncate text-xs text-ink-mute">{wf.agent_id} · updated {ago(wf.updated_at)}</span>
        </span>
        <Chip tone={state.tone}>{state.label}</Chip>
      </button>

      <div id={panelId} hidden={!open} className="pb-5 pl-8 pr-1">
        <ol className="m-0 list-none space-y-4 p-0 text-sm">
          {wf.previous_decisions.map((d, i) => {
            const prop = wf.action_history[i];
            const meta = DECISION[d.decision] ?? { label: humanize(d.decision), tone: 'neutral' as Tone };
            return (
              <li key={d.decision_id ?? i} className="border-l-2 border-rule pl-4">
                <p className="text-xs text-ink-mute">Proposed {dateTime(prop?.proposed_at ?? d.timestamp)}</p>
                <p>{proposalSummary(prop)}{prop && ` to ${prop.recipient}`}</p>
                <p className="mt-1 flex flex-wrap items-center gap-2">
                  <Chip tone={meta.tone}>{meta.label}</Chip>
                  <span className="text-xs text-ink-mute">policy {d.policy_version}</span>
                </p>
                <p className="mt-1 max-w-prose break-words text-ink-soft">{d.reason}</p>
              </li>
            );
          })}

          {review?.required && (
            <li className="border-l-2 border-rule pl-4">
              <p className="text-xs text-ink-mute">Human review</p>
              <p className="mt-1 flex flex-wrap items-center gap-2">
                <Chip tone={REVIEW_TONE[review.status] ?? 'neutral'}>{humanize(review.status)}</Chip>
                {review.decided_by && <span className="text-ink-soft">by {review.decided_by}, {dateTime(review.decided_at)}</span>}
              </p>
              {/* While pending, the backend keeps the policy reason in operator_notes; only a decided review has a human note. */}
              {review.decided_by && review.operator_notes && (
                <p className="mt-1 max-w-prose whitespace-pre-wrap break-words text-ink-soft">Note: {review.operator_notes}</p>
              )}
            </li>
          )}

          {wf.tool_results.map((r, i) => (
            <li key={`exec-${i}`} className="border-l-2 border-rule pl-4">
              <p className="text-xs text-ink-mute">Execution{r.executed_at ? `, ${dateTime(r.executed_at)}` : ''}</p>
              <p className="mt-1 flex flex-wrap items-center gap-2">
                <Chip tone={r.executed ? 'auto' : 'block'}>{r.executed ? 'Executed' : 'Failed'}</Chip>
                {r.notification_id && <span className="text-xs text-ink-mute">receipt {r.notification_id}</span>}
              </p>
              {r.error && <p className="mt-1 break-words text-block">{r.error}</p>}
            </li>
          ))}

          {wf.previous_decisions.length === 0 && <li className="text-ink-mute">No decisions recorded for this workflow.</li>}
        </ol>
      </div>
    </li>
  );
}

export function ActivityView({ workflows, metrics }: { workflows: Source<WorkflowMemoryRecord[]>; metrics: Source<AutonomyMetrics> }) {
  const sorted = useMemo(
    () => [...(workflows.data ?? [])].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)),
    [workflows.data],
  );
  // Agent-proposal figures are counted from the recorded gateway decisions themselves.
  const figures = useMemo(() => {
    if (!workflows.data) return null;
    const decisions = workflows.data.flatMap((w) => w.previous_decisions);
    return {
      sent: workflows.data.reduce((n, w) => n + w.action_history.length, 0),
      needed: decisions.filter((d) => d.decision === 'require_human_approval').length,
      blocked: decisions.filter((d) => d.decision === 'deny').length,
    };
  }, [workflows.data]);

  return (
    <section aria-labelledby="activity-title">
      <ViewHeader
        id="activity-title"
        title="Activity"
        lede="Every action agents proposed, how policy decided, who reviewed it, and whether it ran."
        sources={[workflows, metrics]}
      />

      <dl className="m-0 mt-6 grid grid-cols-2 divide-rule border-b border-rule pb-6 sm:grid-cols-4 sm:divide-x">
        <Figure value={figures?.sent ?? null} label="Actions sent" note="by agents" />
        <Figure value={figures?.needed ?? null} label="Needed a person" note="held by policy" />
        <Figure value={figures?.blocked ?? null} label="Blocked" note="by policy or checks" />
        <Figure value={metrics.data?.duplicate_actions_prevented ?? null} label="Duplicates stopped" note="in expense reminders" />
      </dl>

      <section aria-labelledby="workflows-title" className="mt-10">
        <SectionHeader id="workflows-title" title="Workflows" aside={workflows.data ? `${sorted.length} total, newest first` : undefined} />
        {workflows.data === null ? (
          workflows.error ? <LoadFailed what="workflow history" error={workflows.error} /> : <Loading what="workflow history" />
        ) : sorted.length === 0 ? (
          <Empty title="No workflows yet." hint="Each proposal an agent sends appears here with its decision, any human review, and the execution result." />
        ) : (
          <ul className="m-0 list-none border-t border-rule p-0">
            {sorted.map((wf) => <WorkflowRow key={wf.workflow_id} wf={wf} />)}
          </ul>
        )}
      </section>
    </section>
  );
}
