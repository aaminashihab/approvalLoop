import { formatMoney } from '../lib/format';
import { BandInput, Zone, zoneOf } from '../lib/policy';

const ZONE_NAME: Record<Zone, string> = { auto: 'Runs automatically', review: 'Needs a person', block: 'Blocked' };
const SOLID: Record<Zone, string> = { auto: 'bg-auto', review: 'bg-review', block: 'bg-block' };
const WASH: Record<Zone, string> = { auto: 'bg-auto-wash', review: 'bg-review-wash', block: 'bg-block-wash' };
const TEXT: Record<Zone, string> = { auto: 'text-auto', review: 'text-review', block: 'text-block' };

interface PolicyBandProps {
  band: BandInput;
  currency: string;
  policyVersion: string;
}

/**
 * Where this proposal sits against its policy's limits. Explanatory only: the decision shown on
 * the page came from the server, which is the only thing that enforces these limits.
 */
export function PolicyBand({ band, currency, policyVersion }: PolicyBandProps) {
  const { value, limits } = band;
  const fmt = (n: number) => (limits.unit === 'percent' ? `${n}%` : formatMoney(n, currency, true));
  const zone = zoneOf(value, limits);

  const scaleMax = limits.reviewMax * 1.4;
  const pct = (n: number) => Math.min(100, Math.max(0, (n / scaleMax) * 100));
  const offScale = value > scaleMax;
  const markerPct = pct(value);

  const autoText = `${limits.autoInclusive ? 'up to' : 'under'} ${fmt(limits.autoMax)}`;
  const reviewText = `${limits.autoInclusive ? 'over' : 'from'} ${fmt(limits.autoMax)} to ${fmt(limits.reviewMax)}`;
  const blockText = `above ${fmt(limits.reviewMax)}`;
  const label =
    `${fmt(value)} falls in the "${ZONE_NAME[zone].toLowerCase()}" zone of policy ${policyVersion}. ` +
    `Runs automatically ${autoText}; needs a person ${reviewText}; blocked ${blockText}.`;

  const segments: { z: Zone; from: number; to: number }[] = [
    { z: 'auto', from: 0, to: pct(limits.autoMax) },
    { z: 'review', from: pct(limits.autoMax), to: pct(limits.reviewMax) },
    { z: 'block', from: pct(limits.reviewMax), to: 100 },
  ];
  const align = markerPct < 12 ? 'translate-x-0' : markerPct > 88 ? '-translate-x-full' : '-translate-x-1/2';

  return (
    <section aria-labelledby="band-title">
      <h3 id="band-title" className="text-sm font-medium text-ink-soft">
        Where this falls in policy {policyVersion}
      </h3>

      <div role="img" aria-label={label} className="relative mt-8">
        <div className={`absolute bottom-full mb-2 whitespace-nowrap font-serif text-base font-medium ${align}`} style={{ left: `${markerPct}%` }} aria-hidden="true">
          {fmt(value)}{offScale && ' →'}
        </div>
        <div className="flex h-3 w-full overflow-hidden rounded-sm" aria-hidden="true">
          {segments.map((s) => (
            <div key={s.z} className={s.z === zone ? SOLID[s.z] : WASH[s.z]} style={{ width: `${s.to - s.from}%` }} />
          ))}
        </div>
        <div className="absolute -top-1.5 h-6 w-[3px] -translate-x-1/2 rounded-full bg-ink ring-2 ring-sheet" style={{ left: `${markerPct}%` }} aria-hidden="true" />
      </div>

      <ul className="m-0 mt-3 grid list-none grid-cols-3 gap-3 p-0 text-xs">
        {([['auto', autoText], ['review', reviewText], ['block', blockText]] as [Zone, string][]).map(([z, text]) => (
          <li key={z} className={z === zone ? 'text-ink' : 'text-ink-mute'}>
            <span className={`block font-medium ${TEXT[z]}`}>
              {ZONE_NAME[z]}{z === zone && <span className="sr-only"> (this proposal)</span>}
            </span>
            {text}
          </li>
        ))}
      </ul>
    </section>
  );
}
