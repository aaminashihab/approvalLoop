import { FormEvent, ReactNode, useState } from 'react';
import { Activity, AlertTriangle, Bot, FlaskConical, Inbox, KeyRound, Receipt } from 'lucide-react';
import { Button } from './ui';

export type ViewId = 'approvals' | 'activity' | 'agents' | 'expenses' | 'sandbox';

export const NAV: { id: ViewId; label: string; Icon: typeof Inbox }[] = [
  { id: 'approvals', label: 'Approvals', Icon: Inbox },
  { id: 'activity', label: 'Activity', Icon: Activity },
  { id: 'agents', label: 'Agents', Icon: Bot },
  { id: 'expenses', label: 'Expenses', Icon: Receipt },
  { id: 'sandbox', label: 'Sandbox', Icon: FlaskConical },
];

interface ShellProps {
  view: ViewId;
  pendingCount: number | null;
  hasKey: boolean;
  keyRejected: boolean;
  showKeyForm: boolean;
  onOpenKeyForm: () => void;
  onSaveKey: (key: string) => void;
  onForgetKey: () => void;
  connection: { title: string; detail: string } | null;
  children: ReactNode;
}

function KeyForm({ rejected, hasKey, onSave }: { rejected: boolean; hasKey: boolean; onSave: (key: string) => void }) {
  const [value, setValue] = useState('');
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) { onSave(value.trim()); setValue(''); }
  };
  return (
    <section role={rejected ? 'alert' : undefined} aria-labelledby="key-title" className="mb-8 border-l-4 border-review bg-review-wash px-4 py-4">
      <h2 id="key-title" className="flex items-center gap-2 text-sm font-medium text-review">
        <KeyRound className="h-4 w-4" aria-hidden="true" />
        {rejected
          ? hasKey ? 'The server did not accept this operator key.' : 'An operator key is required to see and decide approvals.'
          : 'Enter an operator key.'}
      </h2>
      <form onSubmit={submit} className="mt-3 flex max-w-md flex-col gap-2 sm:flex-row">
        <label htmlFor="operator-key" className="sr-only">Operator key</label>
        <input
          id="operator-key"
          type="password"
          autoComplete="off"
          spellCheck={false}
          placeholder="Operator key"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="min-h-touch flex-1 rounded border border-ink/30 bg-sheet px-3 text-sm placeholder:text-ink-mute"
        />
        <Button kind="primary" type="submit" disabled={!value.trim()}>Use this key</Button>
      </form>
      <p className="mt-2 text-xs text-ink-soft">
        Kept only in this browser tab and cleared when the tab closes. Your decisions are recorded under the identity this key belongs to.
      </p>
    </section>
  );
}

function KeyStatus({ hasKey, onOpen, onForget }: { hasKey: boolean; onOpen: () => void; onForget: () => void }) {
  return hasKey ? (
    <div className="text-xs text-ink-mute">
      <p>Operator key saved in this tab.</p>
      <button type="button" onClick={onForget} className="mt-1 min-h-touch font-medium text-ink underline underline-offset-2">
        Forget key
      </button>
    </div>
  ) : (
    <div className="text-xs text-ink-mute">
      <p>No operator key in this tab.</p>
      <button type="button" onClick={onOpen} className="mt-1 min-h-touch font-medium text-ink underline underline-offset-2">
        Enter key
      </button>
    </div>
  );
}

export function Shell(p: ShellProps) {
  const badge = (active: boolean) =>
    p.pendingCount !== null && p.pendingCount > 0 ? (
      <span className={`ml-auto rounded-sm px-1.5 text-xs font-semibold ${active ? 'bg-sheet text-ink' : 'bg-review text-sheet'}`}>
        {p.pendingCount}<span className="sr-only"> waiting</span>
      </span>
    ) : null;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[232px_minmax(0,1fr)]">
      <aside className="hidden border-r border-rule md:block">
        <div className="sticky top-0 flex h-screen flex-col px-5 py-7">
          <p className="font-serif text-2xl font-semibold">ApprovalLoop</p>
          <p className="mt-1 text-xs text-ink-mute">Agents propose. Policy decides. People sign off.</p>
          <nav aria-label="Main" className="mt-8">
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {NAV.map(({ id, label, Icon }) => {
                const active = p.view === id;
                return (
                  <li key={id}>
                    <a
                      href={`#${id}`}
                      aria-current={active ? 'page' : undefined}
                      className={`flex min-h-touch items-center gap-3 rounded px-3 text-sm ${active ? 'bg-ink font-medium text-sheet' : 'text-ink-soft hover:bg-sheet'}`}
                    >
                      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      {label}
                      {id === 'approvals' && badge(active)}
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
          <div className="mt-auto border-t border-rule pt-4">
            <KeyStatus hasKey={p.hasKey} onOpen={p.onOpenKeyForm} onForget={p.onForgetKey} />
          </div>
        </div>
      </aside>

      <div className="min-w-0 pb-24 md:pb-12">
        <header className="flex items-center justify-between gap-3 border-b border-rule bg-sheet px-4 py-2 md:hidden">
          <p className="font-serif text-xl font-semibold">ApprovalLoop</p>
          <button
            type="button"
            onClick={p.hasKey ? p.onForgetKey : p.onOpenKeyForm}
            className="inline-flex min-h-touch items-center gap-2 px-1 text-xs font-medium text-ink"
          >
            <KeyRound className="h-4 w-4" aria-hidden="true" />
            {p.hasKey ? 'Forget key' : 'Enter key'}
          </button>
        </header>

        <main className="mx-auto max-w-content px-4 py-6 sm:px-6 md:px-10 md:py-10">
          {p.connection && (
            <div role="alert" className="mb-6 flex gap-3 border-l-4 border-block bg-block-wash px-4 py-3 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-block" aria-hidden="true" />
              <div>
                <p className="font-medium text-block">{p.connection.title}</p>
                <p className="mt-0.5 text-ink">{p.connection.detail}</p>
              </div>
            </div>
          )}
          {p.showKeyForm && <KeyForm rejected={p.keyRejected} hasKey={p.hasKey} onSave={p.onSaveKey} />}
          {p.children}
        </main>
      </div>

      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-10 border-t border-rule bg-sheet pb-[env(safe-area-inset-bottom)] md:hidden">
        <ul className="m-0 grid list-none grid-cols-5 p-0">
          {NAV.map(({ id, label, Icon }) => {
            const active = p.view === id;
            return (
              <li key={id}>
                <a
                  href={`#${id}`}
                  aria-current={active ? 'page' : undefined}
                  className={`relative flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-[11px] ${active ? 'font-semibold text-ink' : 'text-ink-mute'}`}
                >
                  {active && <span className="absolute inset-x-3 top-0 h-[3px] bg-ink" aria-hidden="true" />}
                  <Icon className="h-5 w-5" aria-hidden="true" />
                  {label}
                  {id === 'approvals' && p.pendingCount !== null && p.pendingCount > 0 && (
                    <span className="absolute right-1/2 top-1.5 translate-x-5 rounded-sm bg-review px-1 text-[10px] font-semibold leading-4 text-sheet">
                      {p.pendingCount}<span className="sr-only"> waiting</span>
                    </span>
                  )}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
