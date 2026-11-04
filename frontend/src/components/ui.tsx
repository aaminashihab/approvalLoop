import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { clockTime } from '../lib/format';
import type { Source } from '../lib/useConsoleData';

export type Tone = 'auto' | 'review' | 'block' | 'neutral';

const CHIP: Record<Tone, string> = {
  auto: 'bg-auto-wash text-auto',
  review: 'bg-review-wash text-review',
  block: 'bg-block-wash text-block',
  neutral: 'bg-paper text-ink-soft',
};

/** A status label. Color supports the text; the text alone always carries the meaning. */
export function Chip({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-sm px-2 py-0.5 text-xs font-medium ${CHIP[tone]}`}>
      {children}
    </span>
  );
}

type ButtonKind = 'primary' | 'secondary' | 'danger';
const BUTTON: Record<ButtonKind, string> = {
  primary: 'border border-ink bg-ink text-sheet hover:bg-ink-soft disabled:border-ink-mute disabled:bg-ink-mute',
  secondary: 'border border-ink/40 bg-sheet text-ink hover:border-ink disabled:border-rule disabled:text-ink-mute',
  danger: 'border border-block/60 bg-sheet text-block hover:border-block disabled:border-rule disabled:text-ink-mute',
};

export function Button({ kind = 'secondary', className = '', type = 'button', ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { kind?: ButtonKind }) {
  return (
    <button
      type={type}
      {...rest}
      className={`inline-flex min-h-touch items-center justify-center gap-2 rounded px-4 text-sm font-medium disabled:cursor-not-allowed ${BUTTON[kind]} ${className}`}
    />
  );
}

/** The page heading for a view: exactly one h1 per view. */
export function ViewHeader({ id, title, lede, sources }: { id: string; title: ReactNode; lede: ReactNode; sources: Source<unknown>[] }) {
  return (
    <header className="flex flex-col gap-2 border-b border-rule pb-5 sm:flex-row sm:items-end sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <h1 id={id} className="font-serif text-3xl font-medium leading-tight sm:text-4xl">{title}</h1>
        <p className="mt-2 max-w-xl text-sm text-ink-mute">{lede}</p>
      </div>
      <Freshness sources={sources} />
    </header>
  );
}

/** States when the view's data was last confirmed by the server, and says so plainly when it may be stale. */
export function Freshness({ sources }: { sources: Source<unknown>[] }) {
  const loaded = sources.filter((s) => s.updatedAt !== null);
  if (sources.length === 0 || loaded.length < sources.length) return null;
  const oldest = Math.min(...loaded.map((s) => s.updatedAt as number));
  const stale = sources.some((s) => s.error);
  return stale ? (
    <p className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-block">
      <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
      May be out of date. Last confirmed {clockTime(oldest)}
    </p>
  ) : (
    <p className="shrink-0 text-xs text-ink-mute">Updated {clockTime(oldest)}</p>
  );
}

export function SectionHeader({ id, title, aside }: { id: string; title: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-4">
      <h2 id={id} className="font-serif text-xl font-medium">{title}</h2>
      {aside !== undefined && <p className="text-sm text-ink-mute">{aside}</p>}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <p role="status" className="border-b border-rule py-8 text-sm text-ink-mute">
      Loading {what}…
    </p>
  );
}

export function Empty({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="border-b border-rule py-8">
      <p className="font-serif text-xl">{title}</p>
      <p className="mt-1 max-w-md text-sm text-ink-mute">{hint}</p>
    </div>
  );
}

/** Shown in place of a list when it has never loaded. The global banner explains the retry. */
export function LoadFailed({ what, error }: { what: string; error: { message: string } }) {
  return (
    <div className="border-b border-rule py-8">
      <p className="font-serif text-xl">Couldn't load {what}.</p>
      <p className="mt-1 max-w-md text-sm text-ink-mute">{error.message} Retrying automatically.</p>
    </div>
  );
}

const NOTICE = {
  ok: 'border-auto bg-auto-wash text-auto',
  done: 'border-ink bg-sheet text-ink',
  warn: 'border-review bg-review-wash text-review',
  error: 'border-block bg-block-wash text-block',
};

/**
 * Feedback for something the operator just did: role="status" for confirmations, role="alert" for problems.
 * "ok" (teal) is for things that ran; "done" (neutral) confirms an action that stopped something, such as a rejection.
 */
export function Notice({ tone, title, children }: { tone: keyof typeof NOTICE; title: string; children?: ReactNode }) {
  const Icon = tone === 'ok' || tone === 'done' ? CheckCircle2 : AlertTriangle;
  const style = NOTICE[tone];
  return (
    <div role={tone === 'ok' || tone === 'done' ? 'status' : 'alert'} className={`flex gap-3 border-l-4 px-4 py-3 text-sm ${style}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <p className="font-medium">{title}</p>
        {children && <div className="mt-0.5 break-words text-ink">{children}</div>}
      </div>
    </div>
  );
}
