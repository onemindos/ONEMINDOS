// SPDX-License-Identifier: Apache-2.0
// The Control Hub's live panels (FD-05, #502): alerts, storage, backups, A/B system slots and the
// Kubernetes view. Read-only: each links to the screen that acts on it. Data comes from useBoard
// (ControlHubLive.tsx) and the shared hub; nothing here invents a value the hub did not report.
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { Card, StatusPill, formatAgo, formatBytes, secondsSince, type BackupStatus, type StorageStatus, type Tone } from '@onemind/ui';
import type { NodeRecord } from '../api/types';
import type { AlertInfo } from '../api/wiring';
import type { Polled } from '../lib/hooks';
import { href } from '../shell/routes';
import { Load } from './parts';
import { staleNote } from './ControlHubLive';

/** A panel: its card turns "stale" with a note when the data on screen is not current. */
export function Panel<T>({ title, res, now, what, children }: { title: string; res: Polled<T>; now: number; what: string; children: (data: T) => ReactNode }) {
  const note = staleNote(res, now);
  return (
    <Card title={title} variant={note ? 'stale' : 'default'}>
      {note && <p className="om-note om-tone-warn" role="status">{note}</p>}
      <Load res={res} what={what}>{children}</Load>
    </Card>
  );
}

const SEVERITY_TONE: Record<string, Tone> = { critical: 'bad', warning: 'warn', info: 'info' };
const SEVERITY_RANK: Record<string, number> = { critical: 0, warning: 1, info: 2 };
/** How many alerts the board lists; the Alerts screen has all of them. */
export const ALERTS_SHOWN = 5;

export function AlertsList({ alerts, now }: { alerts: AlertInfo[]; now: number }) {
  if (alerts.length === 0) return <p className="om-hint">No open alerts.</p>;
  const rows = [...alerts].sort((a, b) => (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3) || Date.parse(b.updated_at) - Date.parse(a.updated_at));
  return (
    <>
      <ul className="dash-list" aria-label="Open alerts">
        {rows.slice(0, ALERTS_SHOWN).map((a) => (
          <li key={a.id}>
            <StatusPill tone={SEVERITY_TONE[a.severity] ?? 'neutral'} label={a.severity} detail={formatAgo(secondsSince(a.updated_at, now))} /> {a.title}
          </li>
        ))}
      </ul>
      <p><Link to={href.alerts}>{alerts.length > ALERTS_SHOWN ? `All ${alerts.length} open alerts` : 'Open Alerts'}</Link></p>
    </>
  );
}

export function StorageFacts({ s }: { s: StorageStatus | null }) {
  if (!s || s.state === null) return <p className="om-hint">This box does not report storage.</p>;
  return (
    <>
      <dl className="om-facts">
        <div><dt>State</dt><dd>{s.state}</dd></div>
        <div><dt>Encrypted</dt><dd>{s.encrypted === null ? 'unknown' : s.encrypted ? 'yes' : 'no'}</dd></div>
        <div><dt>Data used</dt><dd>{s.used_bytes === null ? 'unknown' : formatBytes(s.used_bytes)}</dd></div>
        <div><dt>Disks</dt><dd>{s.disks}</dd></div>
      </dl>
      <p><Link to={href.storage}>Open Storage</Link></p>
    </>
  );
}

const BACKUP_TONE: Record<string, Tone> = { ok: 'ok', behind: 'warn', failing: 'bad' };

export function BackupFacts({ b, now }: { b: BackupStatus | null; now: number }) {
  if (!b) return <p className="om-hint">This box does not report backups.</p>;
  const state = b.destinations[0]?.state;
  return (
    <>
      <dl className="om-facts">
        <div><dt>Health</dt><dd>{state ? <StatusPill tone={BACKUP_TONE[state] ?? 'neutral'} label={state} /> : 'no destination yet'}</dd></div>
        <div><dt>Last backup</dt><dd>{b.last_run ? formatAgo(secondsSince(b.last_run, now)) : 'never'}</dd></div>
        <div><dt>Last restore test</dt><dd>{b.last_verified_restore ? formatAgo(secondsSince(b.last_verified_restore, now)) : 'never proved'}</dd></div>
        <div><dt>Destinations</dt><dd>{b.destinations.length}</dd></div>
      </dl>
      <p><Link to={href.backups}>Open Backups</Link></p>
    </>
  );
}

/** One RAUC slot as the heartbeat reports it (internal/heartbeat Slot); malformed entries are dropped. */
export interface SlotInfo { name: string; state?: string; boot_status?: string; bundle_version?: string }
export function slotsOf(n: Pick<NodeRecord, 'rauc'>): SlotInfo[] {
  const str = (v: unknown) => (typeof v === 'string' && v ? v : undefined);
  return (Array.isArray(n.rauc?.slots) ? n.rauc.slots : []).flatMap((x) => {
    const r = x && typeof x === 'object' ? (x as Record<string, unknown>) : {};
    const name = str(r.name);
    return name ? [{ name, state: str(r.state), boot_status: str(r.boot_status), bundle_version: str(r.bundle_version) }] : [];
  });
}

/** The A/B system slots per machine: which one booted and how each slot reports itself. */
export function SlotList({ nodes }: { nodes: NodeRecord[] }) {
  if (nodes.length === 0) return <p className="om-hint">No machines have reported yet.</p>;
  return (
    <ul className="dash-list" aria-label="A/B slots by machine">
      {nodes.map((n) => {
        const slots = slotsOf(n);
        return (
          <li key={n.node_id}>
            <strong>{n.hostname}</strong>:{' '}
            {n.rauc?.present ? `running slot ${n.rauc.booted_slot ?? 'unknown'}` : 'no A/B system slots'}
            {slots.length > 0 && (
              <ul>
                {slots.map((s) => (
                  <li key={s.name}>{[s.name, s.state, s.boot_status && `boot ${s.boot_status}`, s.bundle_version && `version ${s.bundle_version}`].filter(Boolean).join(', ')}</li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Pro only: each machine's k3s membership and readiness, from its heartbeat. */
export function KubernetesList({ nodes }: { nodes: NodeRecord[] }) {
  if (nodes.length === 0) return <p className="om-hint">No machines have reported yet.</p>;
  return (
    <ul className="dash-list" aria-label="Kubernetes by machine">
      {nodes.map((n) => (
        <li key={n.node_id}>
          <strong>{n.hostname}</strong>:{' '}
          {n.k3s?.present ? <StatusPill tone={n.k3s.ready ? 'ok' : 'warn'} label={n.k3s.ready ? 'ready' : 'not ready'} detail={n.k3s.role ?? 'member'} /> : 'not in the cluster'}
        </li>
      ))}
    </ul>
  );
}
