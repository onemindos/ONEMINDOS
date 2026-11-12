// SPDX-License-Identifier: Apache-2.0
import type { AppTier, CatalogApp } from '../api/types';
import type { DecideAbility } from '../session';
import { formatDay, installBlockReason, safeHttpUrl } from '../lib/scan';

const LINKS: Array<[keyof CatalogApp['links'], string]> = [
  ['docs', 'Docs'],
  ['github', 'GitHub'],
  ['website', 'Website'],
  ['support', 'Support'],
];

/** Docs, GitHub, website and support links (§9.3, §11.4); missing ones are left out. */
export function AppLinksList({ app }: { app: CatalogApp }) {
  const items = LINKS.map(([key, label]) => [label, safeHttpUrl(app.links?.[key])] as const).filter(
    (x): x is readonly [string, string] => x[1] !== undefined,
  );
  // Older gateways without links: fall back to the §4 source URL.
  const source = safeHttpUrl(app.source);
  if (items.length === 0 && source) items.push(['Source', source]);
  if (items.length === 0) return <p className="small">No links published.</p>;
  return (
    <ul className="app-links" aria-label={`Links for ${app.name}`}>
      {items.map(([label, href]) => (
        <li key={label}>
          <a href={href} target="_blank" rel="noreferrer noopener" className="small">
            {label}
            <span className="visually-hidden"> for {app.name} (opens in a new tab)</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

const TIER_TEXT: Record<AppTier, string> = { verified: 'Verified', community: 'Community', blocked: 'Blocked' };

export function TierBadge({ tier }: { tier: AppTier | null }) {
  return <span className={`badge badge-tier-${tier ?? 'none'}`}>{tier ? TIER_TEXT[tier] : 'Not rated'}</span>;
}

function scanText(app: CatalogApp): string {
  if (!app.scan) return 'Not scanned';
  return `${formatDay(app.scan.scanned_at)} · ${app.scan.result === 'pass' ? 'passed' : 'failed'}`;
}

/** Licence, tier and last scan, shown next to Install (§9.3, §11.4). */
export function TrustFacts({ app }: { app: CatalogApp }) {
  return (
    <>
      <div>
        <dt>Licence</dt>
        <dd>{app.license || 'unknown'}</dd>
      </div>
      <div>
        <dt>Tier</dt>
        <dd>
          <TierBadge tier={app.tier ?? null} />
        </dd>
      </div>
      <div>
        <dt>Last scan</dt>
        <dd>{scanText(app)}</dd>
      </div>
    </>
  );
}

const IN_FLIGHT: Record<string, string> = { installing: 'Installing…', removing: 'Removing…' };

/**
 * Install / Remove button. Install is disabled, with the reason written next to it, when the
 * scan is missing, failing or stale (§10.3); the gateway would refuse the approval anyway.
 * Remove is never blocked by a scan.
 */
export function RequestButton({
  app,
  hubNow,
  busy,
  canRequest,
  onRequest,
}: {
  app: CatalogApp;
  hubNow: number;
  busy: string | undefined;
  canRequest: DecideAbility;
  onRequest: (app: CatalogApp) => void;
}) {
  const inFlight = IN_FLIGHT[app.status];
  const blocked = app.installed ? undefined : installBlockReason(app, hubNow);
  const reasonId = `install-reason-${app.id}`;
  return (
    <div className="request">
      <button
        type="button"
        className={app.installed ? 'btn btn-ghost' : 'btn btn-primary'}
        disabled={busy !== undefined || canRequest === 'no' || inFlight !== undefined || blocked !== undefined}
        aria-describedby={blocked ? reasonId : undefined}
        onClick={() => onRequest(app)}
      >
        {busy === app.id
          ? 'Requesting…'
          : inFlight
            ? `${inFlight.slice(0, -1)} ${app.name}…`
            : app.installed
              ? `Remove ${app.name}`
              : `Install ${app.name}`}
      </button>
      {blocked && (
        <p id={reasonId} className="install-reason small">
          {blocked}
        </p>
      )}
    </div>
  );
}

export { IN_FLIGHT };
