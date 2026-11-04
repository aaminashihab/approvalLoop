import type { ReactNode } from 'react';
import { Chip, Empty, LoadFailed, Loading, Tone, ViewHeader } from '../components/ui';
import { humanize } from '../lib/format';
import type { Source } from '../lib/useConsoleData';
import type { AgentRegistration } from '../types/approval';

const STATUS_TONE: Record<AgentRegistration['status'], Tone> = { active: 'auto', disabled: 'block', deprecated: 'review' };

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-mute">{label}</dt>
      <dd className="m-0 break-words text-sm">{children}</dd>
    </div>
  );
}

export function AgentsView({ agents }: { agents: Source<AgentRegistration[]> }) {
  const list = agents.data ? [...agents.data].sort((a, b) => a.name.localeCompare(b.name)) : null;
  return (
    <section aria-labelledby="agents-title">
      <ViewHeader
        id="agents-title"
        title="Agents"
        lede="Registered agents. Each can only propose the actions listed for it, and every proposal is checked against its policy profile."
        sources={[agents]}
      />
      {list === null ? (
        agents.error ? <LoadFailed what="the agent registry" error={agents.error} /> : <Loading what="the agent registry" />
      ) : list.length === 0 ? (
        <Empty title="No agents registered." hint="Agents appear here once they are added to the registry through the registry API." />
      ) : (
        <ul className="m-0 list-none p-0">
          {list.map((a) => (
            <li key={a.agent_id} className="grid gap-x-10 gap-y-4 border-b border-rule py-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
              <div className="min-w-0">
                <h2 className="font-serif text-2xl font-medium leading-tight">{a.name}</h2>
                <p className="mt-0.5 text-sm text-ink-mute">{a.agent_id} · version {a.version}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Chip tone={STATUS_TONE[a.status] ?? 'neutral'}>{humanize(a.status)}</Chip>
                  {/* Risk is a property, not a decision: it stays neutral so color keeps meaning allowed / held / blocked. */}
                  <Chip tone="neutral">{humanize(a.risk_level)} risk</Chip>
                </div>
                {a.description && <p className="mt-3 max-w-prose text-sm text-ink-soft">{a.description}</p>}
              </div>
              <dl className="m-0 grid content-start gap-3">
                <Field label="Policy profile">{a.policy_profile}</Field>
                <Field label="Allowed actions">{a.allowed_actions.length ? a.allowed_actions.map(humanize).join(', ') : 'None'}</Field>
                <Field label="Owner">{a.owner}</Field>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
