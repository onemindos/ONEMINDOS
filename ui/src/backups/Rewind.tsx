// SPDX-License-Identifier: Apache-2.0
// Rewind (BACKUPS.md §7.1): pick a restore point, browse it like a folder, download one file, or
// ask to put one file or the whole app back. Browsing is owner-only and each read is audited by
// the hub; the screen says so. Restoring is always a request that waits for approval.
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { formatAgo, formatDay, secondsSince } from '../lib/time';
import { REASON, breadcrumbs, formatBytes, snapshotsByDay, volumeLabel } from './logic';
import './backups.css';
import type { Load, Snapshot, TreeEntry } from './types';

export interface RewindProps {
  appId: string;
  snapshots: Load<Snapshot[]>;
  selected?: Snapshot;
  /** Folder shown in the browser; undefined lists the snapshot's volumes. */
  path?: string;
  entries: Load<TreeEntry[]> | null;
  now: number;
  onSelect: (s: Snapshot) => void;
  onOpen: (path: string | undefined) => void;
  /** URL that downloads one file (the dashboard adds its token). */
  fileHref: (s: Snapshot, path: string) => string;
  onRestoreApp: (s: Snapshot) => void;
  onRestorePath: (s: Snapshot, path: string) => void;
}

export function Rewind(p: RewindProps) {
  return (
    <section className="omb-rewind" aria-labelledby="omb-rewind-title">
      <h1 id="omb-rewind-title" className="omb-title">Rewind {p.appId}</h1>
      <p className="om-hint">
        <Icon name="lock" /> Only the owner can open backups, and every folder you open here is recorded in the activity log.
      </p>
      <div className="omb-rewind-cols">
        <nav aria-label="Restore points" className="omb-points">
          <PointList {...p} />
        </nav>
        <div className="omb-browser">
          {!p.selected ? (
            <EmptyState icon="clock" title="Pick a restore point">Each one is the app’s data at that moment.</EmptyState>
          ) : (
            <Browser {...p} snap={p.selected} />
          )}
        </div>
      </div>
    </section>
  );
}

function PointList(p: RewindProps) {
  if (p.snapshots.status === 'loading') return <p className="om-hint" role="status">Loading restore points…</p>;
  if (p.snapshots.status === 'error') return <p className="omb-error" role="alert">{p.snapshots.code}: {p.snapshots.message}</p>;
  const days = snapshotsByDay(p.snapshots.data, p.appId);
  if (!days.length) return <p className="om-hint">No backup of {p.appId} yet.</p>;
  return (
    <ol className="omb-days">
      {days.map((d) => (
        <li key={d.day}>
          <h2 className="om-subhead">{formatDay(`${d.day}T00:00:00Z`)}</h2>
          <ul>
            {d.items.map((s) => (
              <li key={s.id}>
                <button type="button" className="omb-point" aria-current={p.selected?.id === s.id ? 'true' : undefined} onClick={() => p.onSelect(s)}>
                  <span>{s.taken_at.slice(11, 16)} UTC · {formatAgo(secondsSince(s.taken_at, p.now))}</span>
                  <span className="om-hint">{REASON[s.reason] ?? s.reason}</span>
                  {s.verified_at && <StatusPill tone="ok" label="Restore tested" />}
                </button>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

function Browser(p: RewindProps & { snap: Snapshot }) {
  const { snap } = p;
  const crumbs = p.path ? breadcrumbs(p.path, snap.paths) : [];
  return (
    <>
      <div className="omb-browser-head">
        <nav aria-label="Folder" className="omb-crumbs">
          <button type="button" className="omb-link" onClick={() => p.onOpen(undefined)}>Snapshot {snap.short_id}</button>
          {crumbs.map((c) => (
            <span key={c.path}>
              {' / '}
              <button type="button" className="omb-link" onClick={() => p.onOpen(c.path)}>{c.label}</button>
            </span>
          ))}
        </nav>
        <Button variant="primary" onClick={() => p.onRestoreApp(snap)}>Restore all of {p.appId}…</Button>
      </div>
      {!p.path ? (
        <ul className="omb-entries">
          {snap.paths.map((v) => (
            <li key={v}>
              <button type="button" className="omb-link" onClick={() => p.onOpen(v)}>
                <Icon name="backups" /> {volumeLabel(v)}
              </button>
            </li>
          ))}
        </ul>
      ) : p.entries === null || p.entries.status === 'loading' ? (
        <p className="om-hint" role="status">Opening…</p>
      ) : p.entries.status === 'error' ? (
        <p className="omb-error" role="alert">{p.entries.code}: {p.entries.message}</p>
      ) : (
        <ul className="omb-entries">
          {p.entries.data.length === 0 && <li className="om-hint">This folder is empty.</li>}
          {p.entries.data.map((e) => (
            <li key={e.path}>
              {e.type === 'dir' ? (
                <button type="button" className="omb-link" onClick={() => p.onOpen(e.path)}>{e.name}/</button>
              ) : (
                <span>{e.name}</span>
              )}
              <span className="om-hint">{e.type === 'file' ? formatBytes(e.size) : ''}</span>
              <span className="omb-entry-actions">
                {e.type === 'file' && (
                  <a className="omb-link" href={p.fileHref(snap, e.path)} download={e.name}>Download</a>
                )}
                {(e.type === 'file' || e.type === 'dir') && (
                  <Button size="sm" variant="ghost" onClick={() => p.onRestorePath(snap, e.path)} aria-label={`Put ${e.name} back`}>
                    Put back…
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
