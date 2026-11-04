import { ReactNode, RefObject, useMemo, useRef, useState } from 'react';
import { Check, CheckCircle2, KeyRound, X, XCircle } from 'lucide-react';
import { api, ApiError, errorMessage } from '../api/client';
import { PolicyBand } from '../components/PolicyBand';
import { Button, Empty, LoadFailed, Loading, Notice, ViewHeader } from '../components/ui';
import { age, formatMoney, humanize } from '../lib/format';
import { bandFor } from '../lib/policy';
import type { Source } from '../lib/useConsoleData';
import type { AgentRegistration, PendingAction } from '../types/approval';

const NOTE_MAX = 500;

interface Outcome {
  tone: 'ok' | 'done' | 'error';
  title: string;
  body: string;
}

/** The figure a person is deciding on: money, or a discount percentage for sales proposals. */
function headline(p: PendingAction['proposal']): string {
  if (p.amount !== null && p.amount !== undefined && p.amount !== '') return formatMoney(p.amount, p.currency);
  const pct = p.parameters?.discount_percent;
  if (pct !== undefined && pct !== null && pct !== '') return `${pct}% discount`;
  return 'No amount given';
}

function failureTitle(e: unknown): string {
  if (!(e instanceof ApiError)) return 'The decision was not sent.';
  if (e.status === 410) return 'This approval has expired.';
  if (e.status === 409) return 'This action cannot be decided right now.';
  if (e.status === 404) return 'This action was not found.';
  if (e.status === 401 || e.status === 403) return 'Your operator key was not accepted.';
  if (e.status === 0) return 'The server could not be reached.';
  return 'The decision was not recorded.';
}

interface ViewProps {
  pending: Source<PendingAction[]>;
  agents: Source<AgentRegistration[]>;
  refresh: () => Promise<void>;
}

export function ApprovalsView({ pending, agents, refresh }: ViewProps) {
  const queue = useMemo(
    () => [...(pending.data ?? [])].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at)),
    [pending.data],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  const topRef = useRef<HTMLElement>(null);
  const now = Date.now();

  const selected = queue.find((p) => p.action_id === selectedId) ?? queue[0] ?? null;

  const select = (id: string) => {
    setSelectedId(id);
    setOutcome(null);
    // On narrow screens the decision sits below the queue: bring it into view.
    if (window.matchMedia('(max-width: 1023px)').matches) panelRef.current?.scrollIntoView({ block: 'start' });
  };

  /** Returns null on success, or an error outcome for the panel to show next to its buttons. */
  const decide = async (item: PendingAction, kind: 'approve' | 'reject', notes: string): Promise<Outcome | null> => {
    const idx = queue.findIndex((p) => p.action_id === item.action_id);
    const next = queue[idx + 1] ?? queue[idx - 1] ?? null;
    const subject = `${humanize(item.proposal.action_name)} for ${item.proposal.target_resource_id}`;
    try {
      const res = kind === 'approve' ? await api.approveAction(item.action_id, notes) : await api.rejectAction(item.action_id, notes);
      if (kind === 'reject') {
        setOutcome({ tone: 'done', title: `Rejected: ${subject}. Nothing was executed.`, body: res.decision.reason });
      } else if (res.execution?.executed) {
        setOutcome({ tone: 'ok', title: `Approved and executed: ${subject}.`, body: res.decision.reason });
      } else {
        // The server records the approval even when execution fails; say so rather than claim success.
        setOutcome({ tone: 'error', title: `Approved, but execution failed: ${subject}.`, body: res.decision.reason });
      }
      setSelectedId(next?.action_id ?? null);
      topRef.current?.scrollIntoView({ block: 'start' });
      await refresh();
      return null;
    } catch (e) {
      return { tone: 'error', title: failureTitle(e), body: `${errorMessage(e)} Nothing was changed.` };
    }
  };

  const count = pending.data?.length;
  const title = count === undefined ? 'Approvals' : count === 0 ? 'Approvals' : `${count} ${count === 1 ? 'decision' : 'decisions'} waiting`;

  return (
    <section ref={topRef} aria-labelledby="approvals-title" className="scroll-mt-4">
      <ViewHeader
        id="approvals-title"
        title={title}
        lede="Agent proposals that policy held for a person. Nothing here runs until someone approves it."
        sources={[pending]}
      />

      {outcome && (
        <div className="mt-6">
          <Notice tone={outcome.tone} title={outcome.title}>{outcome.body}</Notice>
        </div>
      )}

      {pending.data === null ? (
        pending.error ? <LoadFailed what="the approval queue" error={pending.error} /> : <Loading what="the approval queue" />
      ) : queue.length === 0 ? (
        <Empty title="You're all caught up." hint="When policy holds an agent's proposal for a person, it appears here with the policy's reason." />
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)] lg:gap-8">
          <nav aria-label="Waiting for a decision" className="lg:self-start">
            <ul className="m-0 list-none border-t border-rule p-0">
              {queue.map((p) => {
                const active = p.action_id === selected?.action_id;
                return (
                  <li key={p.action_id} className="border-b border-rule">
                    <button
                      type="button"
                      onClick={() => select(p.action_id)}
                      aria-current={active ? 'true' : undefined}
                      className={`block min-h-touch w-full px-3 py-3 text-left ${active ? 'bg-sheet shadow-[inset_3px_0_0_theme(colors.review.DEFAULT)]' : 'hover:bg-sheet/70'}`}
                    >
                      <span className="block font-serif text-xl leading-tight">{headline(p.proposal)}</span>
                      <span className="mt-0.5 block truncate text-sm text-ink-soft">
                        {humanize(p.proposal.action_name)} · {p.proposal.target_resource_id}
                      </span>
                      <span className="block truncate text-xs text-ink-mute">
                        {p.proposal.agent_id} · waiting {age(p.created_at, now)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>

          {selected && (
            <DecisionPanel
              key={selected.action_id}
              ref_={panelRef}
              item={selected}
              agent={agents.data?.find((a) => a.agent_id === selected.proposal.agent_id)}
              agentsLoaded={agents.data !== null}
              now={now}
              onDecide={decide}
            />
          )}
        </div>
      )}
    </section>
  );
}

interface PanelProps {
  ref_: RefObject<HTMLElement>;
  item: PendingAction;
  agent: AgentRegistration | undefined;
  agentsLoaded: boolean;
  now: number;
  onDecide: (item: PendingAction, kind: 'approve' | 'reject', notes: string) => Promise<Outcome | null>;
}

function Check_({ ok, label }: { ok: boolean; label: string }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <li className={`flex items-center gap-1.5 ${ok ? 'text-ink' : 'font-medium text-block'}`}>
      <Icon className={`h-4 w-4 shrink-0 ${ok ? 'text-auto' : 'text-block'}`} aria-hidden="true" />
      {label} {ok ? 'passed' : 'failed'}
    </li>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-mute">{label}</dt>
      <dd className="m-0 break-words text-sm">{children}</dd>
    </div>
  );
}

function DecisionPanel({ ref_, item, agent, agentsLoaded, now, onDecide }: PanelProps) {
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null);
  const [failure, setFailure] = useState<Outcome | null>(null);
  const { proposal: p, decision: d } = item;
  const band = bandFor(d.policy_version, p.currency, p.amount, p.parameters);
  const agentInactive = agentsLoaded && (!agent || agent.status !== 'active');

  const run = async (kind: 'approve' | 'reject') => {
    setBusy(kind);
    setFailure(null);
    const err = await onDecide(item, kind, notes.trim());
    // On failure the note is kept so the operator can retry without retyping it.
    if (err) setFailure(err);
    else setNotes('');
    setBusy(null);
  };

  return (
    <article ref={ref_} aria-labelledby="decision-title" className="min-w-0 scroll-mt-4 bg-sheet px-5 py-6 shadow-[0_1px_2px_rgba(23,32,46,0.08),0_8px_24px_-12px_rgba(23,32,46,0.18)] sm:px-8 sm:py-8">
      <p className="text-sm text-ink-soft">
        {humanize(p.action_name)} for <span className="font-medium text-ink">{p.target_resource_id}</span>
      </p>
      <h2 id="decision-title" className="mt-1 break-words font-serif text-5xl font-medium leading-none sm:text-6xl">
        {headline(p)}
      </h2>

      <div className="mt-8">
        {band ? (
          <PolicyBand band={band} currency={p.currency} policyVersion={d.policy_version} />
        ) : (
          <p className="text-xs text-ink-mute">
            No limits chart for policy {d.policy_version}: this console has no copy of its limits. The server's reason below is the authority.
          </p>
        )}
      </div>

      <section aria-labelledby="reason-title" className="mt-8">
        <h3 id="reason-title" className="text-sm font-medium text-ink-soft">Policy engine's reason</h3>
        <p className="mt-1 max-w-prose break-words text-sm">{d.reason}</p>
      </section>

      <dl className="m-0 mt-6 grid grid-cols-1 gap-x-6 gap-y-4 border-t border-rule pt-5 sm:grid-cols-2">
        <Fact label="Proposed by">
          {agent ? `${agent.name} (${p.agent_id}, v${agent.version})` : p.agent_id}
        </Fact>
        <Fact label="Target">{p.target_resource_id}</Fact>
        <Fact label="Recipient">{p.recipient}</Fact>
        <Fact label="Policy version">{d.policy_version}</Fact>
        <Fact label="Waiting">{age(item.created_at, now)}</Fact>
        <Fact label="Checks">
          <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0">
            <Check_ ok={d.identity_verified} label="Identity" />
            <Check_ ok={d.safety_guardrail_passed} label="Safety" />
            <Check_ ok={d.validation_passed} label="Validation" />
          </ul>
        </Fact>
      </dl>

      <figure className="m-0 mt-6 border-l-2 border-rule pl-4">
        {p.justification.trim() ? (
          // Untrusted model output: rendered as plain text only, never as HTML.
          <blockquote className="m-0 max-w-prose whitespace-pre-wrap break-words font-serif text-lg italic leading-snug text-ink-soft">
            {p.justification}
          </blockquote>
        ) : (
          <p className="text-sm text-ink-mute">The agent gave no justification.</p>
        )}
        <figcaption className="mt-2 text-xs text-ink-mute">Written by the agent. It has not been verified.</figcaption>
      </figure>

      <div className="mt-8 border-t border-rule pt-6">
        {agentInactive && (
          <div className="mb-5">
            <Notice tone="warn" title={agent ? `${agent.name} is ${agent.status}.` : `${p.agent_id} is not in the agent registry.`}>
              The server will refuse to execute an approval for an agent that is not active. You can still reject it.
            </Notice>
          </div>
        )}
        <label htmlFor="decision-note" className="block text-sm font-medium">
          Note for the audit record <span className="font-normal text-ink-mute">(optional)</span>
        </label>
        <textarea
          id="decision-note"
          value={notes}
          onChange={(e) => setNotes(e.target.value.slice(0, NOTE_MAX))}
          maxLength={NOTE_MAX}
          rows={3}
          disabled={busy !== null}
          aria-describedby="decision-note-count"
          className="mt-1.5 w-full resize-y rounded border border-ink/30 bg-sheet px-3 py-2 text-sm disabled:bg-paper"
        />
        <p id="decision-note-count" className="mt-1 text-right text-xs text-ink-mute">{notes.length} of {NOTE_MAX} characters</p>

        {failure && (
          <div className="mt-3">
            <Notice tone="error" title={failure.title}>{failure.body}</Notice>
          </div>
        )}
        <div className="mt-3 flex flex-col gap-3 sm:flex-row">
          <Button kind="primary" disabled={busy !== null} onClick={() => void run('approve')} className="sm:min-w-[13rem]">
            <Check className="h-4 w-4" aria-hidden="true" />
            {busy === 'approve' ? 'Approving…' : 'Approve and execute'}
          </Button>
          <Button kind="danger" disabled={busy !== null} onClick={() => void run('reject')}>
            <X className="h-4 w-4" aria-hidden="true" />
            {busy === 'reject' ? 'Rejecting…' : 'Reject'}
          </Button>
        </div>
        <p className="mt-4 flex items-start gap-1.5 text-xs text-ink-mute">
          <KeyRound className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Your decision is recorded under the identity of the operator key in use, not a name typed here.
        </p>
      </div>
    </article>
  );
}
