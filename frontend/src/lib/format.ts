const moneyFormatters = new Map<string, Intl.NumberFormat>();

function moneyFormatter(currency: string, wholeUnits: boolean): Intl.NumberFormat | null {
  const code = currency.toUpperCase();
  const cacheKey = `${code}:${wholeUnits}`;
  const cached = moneyFormatters.get(cacheKey);
  if (cached) return cached;
  try {
    const f = new Intl.NumberFormat(code === 'INR' ? 'en-IN' : 'en-US', {
      style: 'currency',
      currency: code,
      ...(wholeUnits ? { maximumFractionDigits: 0 } : {}),
    });
    moneyFormatters.set(cacheKey, f);
    return f;
  } catch {
    return null; // unknown currency code
  }
}

/** Formats a money amount from the API (amounts arrive as decimal strings). */
export function formatMoney(amount: string | number | null | undefined, currency: string, wholeUnits = false): string {
  if (amount === null || amount === undefined || amount === '') return 'No amount';
  const n = typeof amount === 'number' ? amount : Number(amount);
  if (!Number.isFinite(n)) return String(amount);
  const f = moneyFormatter(currency, wholeUnits);
  return f ? f.format(n) : `${currency} ${n.toFixed(2)}`;
}

/** Compact age such as "4 min" or "2 h". */
export function age(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return 'unknown';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'unknown';
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return 'under a minute';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ${m % 60} min`;
  return `${Math.floor(h / 24)} days`;
}

export function ago(iso: string | null | undefined, now: number = Date.now()): string {
  const a = age(iso, now);
  return a === 'unknown' ? 'at an unknown time' : a === 'under a minute' ? 'just now' : `${a} ago`;
}

export function clockTime(ms: number): string {
  return new Date(ms).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return 'unknown';
  const t = Date.parse(iso);
  return Number.isNaN(t) ? iso : new Date(t).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/** "issue_refund" -> "Issue refund". */
export function humanize(snake: string | null | undefined): string {
  if (!snake) return '';
  const spaced = snake.replace(/[_-]+/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
