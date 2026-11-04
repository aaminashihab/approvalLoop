import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { api, ApiError, errorMessage, ScenarioResult } from '../api/client';
import { Button, Chip, Notice, SectionHeader, Tone, ViewHeader } from '../components/ui';
import { formatMoney, humanize } from '../lib/format';

type Kind = 'a' | 'b' | 'c';

const SCENARIOS: { kind: Kind; title: string; expect: string }[] = [
  { kind: 'a', title: 'Small refund', expect: '₹2,000 from the finance agent. Expected to run automatically.' },
  { kind: 'b', title: 'Medium refund', expect: '₹20,000. Expected to wait in Approvals for a person.' },
  { kind: 'c', title: 'Oversized refund', expect: '₹1,00,000. Expected to be blocked by policy.' },
];

const TOOLS: { id: string; label: string; hint: string; run: () => Promise<unknown> }[] = [
  { id: 'seed', label: 'Load sample expense reports', hint: 'Adds five made-up reports in different states.', run: api.seed },
  { id: 'advance', label: 'Skip ahead 35 seconds', hint: 'Ages every report so reminders fall due.', run: () => api.advanceTime(35) },
  { id: 'tick', label: 'Run the reminder check now', hint: 'Does what the scheduler does: sends reminders that are due.', run: api.runTick },
  { id: 'race', label: 'Simulate a race', hint: 'A report is resolved while its reminder is being sent.', run: api.simulateRace },
  { id: 'adversarial', label: 'Simulate a tampered reminder', hint: 'A poisoned recipient and amount; the validator should block it.', run: api.simulateAdversarial },
  { id: 'failure', label: 'Simulate a delivery failure', hint: 'The provider times out; the reminder is marked for retry.', run: api.simulateNotificationFailure },
  { id: 'reset', label: 'Reset sample reports', hint: 'Restores the five starting reports.', run: api.reset },
];

const DECISION: Record<string, { label: string; tone: Tone }> = {
  allow: { label: 'Allowed', tone: 'auto' },
  require_human_approval: { label: 'Needs a person', tone: 'review' },
  deny: { label: 'Blocked', tone: 'block' },
};

const isProductionRefusal = (e: unknown) => e instanceof ApiError && e.status === 404;

export function SandboxView({ refresh }: { refresh: () => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<{ title: string; data: ScenarioResult } | null>(null);
  const [note, setNote] = useState<{ tone: 'ok' | 'error'; title: string; body?: string } | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  const fail = (what: string, e: unknown) => {
    if (isProductionRefusal(e)) setUnavailable(true);
    setNote({ tone: 'error', title: `${what} did not run.`, body: errorMessage(e) });
  };

  const runScenario = async (kind: Kind, title: string) => {
    setBusy(`scenario-${kind}`);
    setNote(null);
    setResult(null);
    try {
      setResult({ title, data: await api.runScenario(kind) });
      await refresh();
    } catch (e) {
      fail(title, e);
    } finally {
      setBusy(null);
    }
  };

  const runTool = async (label: string, id: string, run: () => Promise<unknown>) => {
    setBusy(id);
    setNote(null);
    try {
      const res = await run();
      const message = res && typeof res === 'object' && 'message' in res && typeof res.message === 'string' ? res.message : undefined;
      setNote({ tone: 'ok', title: `${label}: the server confirmed it ran.`, body: message });
      await refresh();
    } catch (e) {
      fail(label, e);
    } finally {
      setBusy(null);
    }
  };

  const d = result?.data.decision;
  const meta = d ? DECISION[d.decision] ?? { label: humanize(d.decision), tone: 'neutral' as Tone } : null;
  const executed = d?.details?.execution_ok;

  return (
    <section aria-labelledby="sandbox-title">
      <ViewHeader
        id="sandbox-title"
        title="Sandbox"
        lede="Try the system with made-up data. Every control here is disabled when the server runs in production: it answers “not found” and nothing changes."
        sources={[]}
      />

      {unavailable && (
        <div className="mt-6">
          <Notice tone="warn" title="This server does not offer sandbox controls.">
            It is most likely running in production, where these endpoints do not exist. Nothing was changed.
          </Notice>
        </div>
      )}
      {note && <div className="mt-6"><Notice tone={note.tone} title={note.title}>{note.body}</Notice></div>}

      <section aria-labelledby="scenarios-title" className="mt-8">
        <SectionHeader id="scenarios-title" title="Send a refund as the finance agent" />
        <ul className="m-0 list-none border-t border-rule p-0">
          {SCENARIOS.map((s) => (
            <li key={s.kind} className="flex flex-col gap-3 border-b border-rule py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-sm font-medium">{s.title}</p>
                <p className="text-sm text-ink-mute">{s.expect}</p>
              </div>
              <Button disabled={busy !== null} onClick={() => void runScenario(s.kind, s.title)} className="shrink-0 sm:w-40">
                {busy === `scenario-${s.kind}` ? 'Sending…' : 'Send proposal'}
              </Button>
            </li>
          ))}
        </ul>

        {result && d && meta && (
          <div role="status" className="mt-4 bg-sheet px-5 py-5">
            <p className="text-xs text-ink-mute">Server's decision for: {result.title}</p>
            <div className="mt-1 flex flex-wrap items-center gap-3">
              <p className="font-serif text-2xl">{formatMoney(result.data.proposal.amount, result.data.proposal.currency)}</p>
              <Chip tone={meta.tone}>{meta.label}</Chip>
              {d.decision === 'allow' && executed !== undefined && (
                <Chip tone={executed ? 'auto' : 'block'}>{executed ? 'Executed' : 'Execution failed'}</Chip>
              )}
            </div>
            <p className="mt-2 max-w-prose break-words text-sm">{d.reason}</p>
            <p className="mt-1 text-xs text-ink-mute">Policy {d.policy_version}</p>
            {d.decision === 'require_human_approval' && (
              <a href="#approvals" className="mt-3 inline-flex min-h-touch items-center gap-1.5 text-sm font-medium underline underline-offset-2">
                Decide it in Approvals <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </a>
            )}
          </div>
        )}
      </section>

      <section aria-labelledby="tools-title" className="mt-10">
        <SectionHeader id="tools-title" title="Test controls" />
        <ul className="m-0 list-none border-t border-rule p-0">
          {TOOLS.map((t) => (
            <li key={t.id} className="flex flex-col gap-3 border-b border-rule py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-sm font-medium">{t.label}</p>
                <p className="text-sm text-ink-mute">{t.hint}</p>
              </div>
              <Button disabled={busy !== null} onClick={() => void runTool(t.label, t.id, t.run)} className="shrink-0 sm:w-40">
                {busy === t.id ? 'Running…' : 'Run'}
              </Button>
            </li>
          ))}
        </ul>
      </section>
    </section>
  );
}
