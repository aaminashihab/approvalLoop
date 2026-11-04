/**
 * Display-only copy of the backend policy limits, used to draw the policy band.
 *
 * The server is the source of truth: backend/approval_loop/policy/policy_engine.py (PolicyEngine.PROFILES)
 * makes and enforces every decision. These numbers only explain a decision that was already made.
 * Limits are keyed by the exact policy version that evaluated the proposal, so a new or unknown
 * version gets no band rather than a guessed one. Keep this table in step with the backend.
 */

export type Zone = 'auto' | 'review' | 'block';

export interface BandLimits {
  /** Upper edge of the "runs automatically" zone. */
  autoMax: number;
  /** Whether a value exactly at autoMax still runs automatically (sales: yes, money: no). */
  autoInclusive: boolean;
  /** Upper edge (inclusive) of the "needs a person" zone; above it is blocked. */
  reviewMax: number;
  unit: 'money' | 'percent';
}

type MoneyByCurrency = Record<string, { autoMax: number; reviewMax: number }>;

const MONEY: Record<string, MoneyByCurrency> = {
  'finance-v3.2.0': { INR: { autoMax: 5000, reviewMax: 25000 }, USD: { autoMax: 50, reviewMax: 250 } },
  'support-v1.1.0': { INR: { autoMax: 2000, reviewMax: 10000 }, USD: { autoMax: 20, reviewMax: 100 } },
};

const PERCENT: Record<string, { autoMax: number; reviewMax: number; parameter: string }> = {
  'sales-v1.0.0': { autoMax: 10, reviewMax: 30, parameter: 'discount_percent' },
};

export interface BandInput {
  limits: BandLimits;
  value: number;
}

const toNumber = (v: unknown): number | null => {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** Returns the limits and the value to place on the band, or null when the band should be hidden. */
export function bandFor(
  policyVersion: string,
  currency: string,
  amount: string | null | undefined,
  parameters: Record<string, unknown> | undefined,
): BandInput | null {
  const money = MONEY[policyVersion]?.[currency.toUpperCase()];
  if (money) {
    const value = toNumber(amount);
    return value === null ? null : { value, limits: { ...money, autoInclusive: false, unit: 'money' } };
  }
  const pct = PERCENT[policyVersion];
  if (pct) {
    const value = toNumber(parameters?.[pct.parameter]);
    return value === null ? null : { value, limits: { autoMax: pct.autoMax, reviewMax: pct.reviewMax, autoInclusive: true, unit: 'percent' } };
  }
  return null;
}

export function zoneOf(value: number, l: BandLimits): Zone {
  if (l.autoInclusive ? value <= l.autoMax : value < l.autoMax) return 'auto';
  if (value <= l.reviewMax) return 'review';
  return 'block';
}
