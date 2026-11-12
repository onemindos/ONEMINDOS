// SPDX-License-Identifier: Apache-2.0
// "Can I trust this app, and can it run here?" in one card (contract §9.3, §11.1, §11.4;
// backlog APP-B2 public scan record, FAB-P3/APP-B3 placement verdict).
import { formatDay } from '../lib/time';
import { installBlockReason, safeHttpUrl, type AppTier, type ScanSummary } from '../lib/trust';
import { Card } from './Card';
import { Icon } from './Icon';
import { StatusPill } from './StatusPill';

export interface AppTrust {
  id: string;
  name: string;
  version: string;
  license: string;
  /** Market licence class (§11.1): L1 permissive, L2 copyleft OK to run. */
  licenseClass?: 'L1' | 'L2' | 'blocked';
  tier: AppTier | null;
  scan: ScanSummary | null;
  links?: { docs?: string | null; github?: string | null; website?: string | null; support?: string | null };
  archs: string[];
  requires?: { gpu?: boolean; minMemoryMb?: number };
  /** Plain-language permissions the app asks for (network, folders, devices, agent principal). */
  permissions?: string[];
}

export interface Placement {
  /** Node the app would run on, or null when no node fits. */
  node: string | null;
  /** "Why not?" lines for nodes that do not fit. */
  reasons?: string[];
}

const TIER: Record<AppTier, { tone: 'ok' | 'neutral' | 'bad'; label: string }> = {
  verified: { tone: 'ok', label: 'Verified' },
  community: { tone: 'neutral', label: 'Community' },
  blocked: { tone: 'bad', label: 'Blocked' },
};

export function TrustCard({ app, now, placement }: { app: AppTrust; now: number; placement?: Placement }) {
  const block = installBlockReason(app.scan, app.tier, now);
  const fits = placement ? placement.node !== null : true;
  const ok = !block && fits;
  const links = (['docs', 'github', 'website', 'support'] as const)
    .map((k) => [k, safeHttpUrl(app.links?.[k])] as const)
    .filter((x): x is readonly [typeof x[0], string] => x[1] !== undefined);
  const scan = app.scan;
  return (
    <Card
      title="Trust and fit"
      subtitle={`${app.name} ${app.version}`}
      variant={ok ? 'default' : 'attention'}
      aside={<StatusPill tone={ok ? 'ok' : 'bad'} label={ok ? 'Can install' : 'Cannot install'} />}
    >
      <div className="om-verdict" aria-live="polite">
        <Icon name={ok ? 'check' : 'alert'} />
        <div>
          {block && <p>{block}</p>}
          {placement && placement.node && <p>Would run on <strong>{placement.node}</strong>.</p>}
          {placement && !placement.node && <p>No node can run it right now.</p>}
          {placement?.reasons && placement.reasons.length > 0 && (
            <ul className="om-why-not" aria-label="Why other nodes do not fit">
              {placement.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          {ok && !placement && <p>Passed its security scan and is allowed by the Market.</p>}
        </div>
      </div>
      <dl className="om-facts">
        <div>
          <dt>Market tier</dt>
          <dd>{app.tier ? <StatusPill tone={TIER[app.tier].tone} label={TIER[app.tier].label} /> : 'Not rated'}</dd>
        </div>
        <div>
          <dt>Licence</dt>
          <dd>
            {app.license || 'unknown'}
            {app.licenseClass ? ` (${app.licenseClass})` : ''}
          </dd>
        </div>
        <div>
          <dt>Last scan</dt>
          <dd>{scan ? `${formatDay(scan.scanned_at)} · ${scan.result === 'pass' ? 'passed' : 'failed'}` : 'never'}</dd>
        </div>
        {scan && (scan.critical !== undefined || scan.high !== undefined) && (
          <div>
            <dt>Vulnerabilities</dt>
            <dd>
              {scan.critical ?? 0} critical · {scan.high ?? 0} high
            </dd>
          </div>
        )}
        {scan?.malware !== undefined && (
          <div>
            <dt>Malware scan</dt>
            <dd>{scan.malware === 0 ? 'clean' : `${scan.malware} finding(s)`}</dd>
          </div>
        )}
        {scan?.cosign && (
          <div>
            <dt>Image signature</dt>
            <dd>{scan.cosign === 'verified' ? 'verified' : scan.cosign === 'unsigned' ? 'not signed upstream' : 'FAILED'}</dd>
          </div>
        )}
        <div>
          <dt>Runs on</dt>
          <dd>
            {app.archs.join(', ')}
            {app.requires?.minMemoryMb ? ` · ${app.requires.minMemoryMb} MB RAM` : ''}
            {app.requires?.gpu ? ' · GPU' : ''}
          </dd>
        </div>
      </dl>
      {app.permissions && app.permissions.length > 0 && (
        <>
          <h3 className="om-subhead">It will be able to</h3>
          <ul className="om-perm-list">
            {app.permissions.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </>
      )}
      {links.length > 0 && (
        <ul className="om-link-row" aria-label={`Links for ${app.name}`}>
          {links.map(([k, href]) => (
            <li key={k}>
              <a href={href} target="_blank" rel="noreferrer noopener">
                {k === 'github' ? 'Source' : k[0]!.toUpperCase() + k.slice(1)}
                <Icon name="external" size={14} />
                <span className="om-visually-hidden"> (opens in a new tab)</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
