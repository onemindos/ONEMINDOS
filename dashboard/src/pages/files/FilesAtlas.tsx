// SPDX-License-Identifier: Apache-2.0
// Atlas Files (prototype 07): the sidebar (spaces, Photos, disks with health, where the backup copies
// live, machines that cannot be reached), the Copies column, the footer line and the drop zone.
// Everything is read from the hub: GET /v1/files/roots (passed in), GET /v1/backups/status and /runs, the
// owner-only GET /v1/storage/devices and the shared node poll. A value the hub does not give a
// person (a 403 for their role) leaves that part out; nothing is filled in. This file changes nothing:
// uploads still go through Files.tsx's own tus upload.
import { createContext, useContext, useEffect, useMemo, useState, type DragEvent, type ReactNode } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Icon } from '@onemind/ui';
import { human, type FileRoot } from '../../files/api';
import { useHub } from '../../data/hub';
import { usePoll } from '../../lib/hooks';
import { formatAgo, secondsSince } from '../../lib/time';
import { useSignedIn } from '../../session';
import { href } from '../../shell/routes';
import { clock, copiesLabel, copiesOf, copiesSummary, toBackupState, type BackupState } from './copies';
import './files.css';

const Ctx = createContext<BackupState | undefined>(undefined);
const rec = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});

/** Reads a path; a 403 (this role may not read it) is `null`, so the page leaves that part out. */
async function readOrNull(sdk: OneMind, path: string): Promise<unknown | null> {
  try {
    return await sdk.call<unknown>({ method: 'GET', path });
  } catch (e) {
    if (e instanceof OneMindError && e.status === 403) return null;
    throw e;
  }
}

/** The Files window body: sidebar and page, with the backup state shared by the Copies cells. */
export function FilesLayout({ roots, current, onPick, children }: { roots: FileRoot[]; current: FileRoot | undefined; onPick: (r: FileRoot) => void; children: ReactNode }) {
  const { token, account, principal } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const backups = usePoll(async () => {
    const raw = await readOrNull(sdk, '/v1/backups/status');
    if (raw === null) return null;
    const runs = await readOrNull(sdk, '/v1/backups/runs');
    return runs === null ? null : toBackupState(raw, runs);
  }, 60_000);
  // On a real box the role comes from GET /v1/me (account); principal is only known in demo and tests.
  const owner = (account?.role ?? principal?.role) === 'owner';
  const disks = usePoll(async () => (owner ? readOrNull(sdk, '/v1/storage/devices') : null), 60_000);
  useEffect(() => { if (owner) void disks.reload(); }, [owner]); // eslint-disable-line react-hooks/exhaustive-deps
  // A later failed refresh clears the copies: an old answer is never shown as the current count.
  const state = backups.error ? undefined : backups.data ?? undefined;
  return (
    <Ctx.Provider value={state}>
      <div className="dash-files">
        <FilesSidebar roots={roots} current={current} onPick={onPick} backups={state} disks={Array.isArray(disks.data) ? disks.data.map(rec) : undefined} />
        <div className="dash-files-main">{children}</div>
      </div>
    </Ctx.Provider>
  );
}

function FilesSidebar({ roots, current, onPick, backups, disks }: { roots: FileRoot[]; current: FileRoot | undefined; onPick: (r: FileRoot) => void; backups?: BackupState; disks?: Record<string, unknown>[] }) {
  const hub = useHub();
  const away = (hub.nodes.data ?? []).filter((n) => hub.nodeStatus(n) === 'offline');
  return (
    <nav className="dash-files-nav" aria-label="Places">
      <h2 className="dash-files-head">On {hub.instance.data?.name ?? 'this box'}</h2>
      <ul className="dash-files-list" aria-label="Spaces">
        {roots.map((r) => (
          <li key={r.root}>
            <button type="button" className="dash-files-item" aria-pressed={r.root === current?.root} onClick={() => onPick(r)}>
              <Icon name={r.kind === 'home' ? 'user' : r.kind === 'grant' ? 'link' : 'storage'} size={18} />
              <span className="dash-files-label">{r.name}</span>
              {!r.writable && <span className="dash-files-n">read only</span>}
            </button>
          </li>
        ))}
        <li><a className="dash-files-item" href={href.photos}><Icon name="monitor" size={18} /><span className="dash-files-label">Photos</span></a></li>
      </ul>
      {disks && disks.length > 0 && (
        <>
          <h2 className="dash-files-head">Disks</h2>
          <ul className="dash-files-list" aria-label="Disks">
            {disks.map((d, i) => {
              const h = rec(d.health);
              const verdict = typeof h.verdict === 'string' ? h.verdict : 'unknown';
              return (
                <li key={i} className="dash-files-disk">
                  <span className="dash-files-row">
                    <span className={`dash-files-dot dash-files-dot-${verdict === 'ok' ? 'ok' : verdict === 'unknown' ? 'muted' : verdict === 'critical' ? 'bad' : 'warn'}`} aria-hidden="true" />
                    <span className="dash-files-label">{typeof d.model === 'string' ? d.model : typeof d.path === 'string' ? d.path : 'Disk'}</span>
                    <span className="dash-files-n">{human(typeof d.size_bytes === 'number' ? d.size_bytes : null)}</span>
                  </span>
                  <span className="om-hint">Health {verdict}{typeof h.temperature_c === 'number' ? ` · ${h.temperature_c} °C` : ''}{typeof d.role === 'string' ? ` · ${d.role}` : ''}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
      {backups && (
        <>
          <h2 className="dash-files-head">Copies kept elsewhere</h2>
          {!backups.primary ? (
            <p className="om-hint dash-files-pad">No backup destination yet. Set one up in <a href={href.backups}>Backups</a>.</p>
          ) : (
            <ul className="dash-files-list" aria-label="Backup destinations">
              <li className="dash-files-disk">
                <span className="dash-files-row"><span className={`dash-files-dot dash-files-dot-${backups.lastPrimaryCopyAt ? 'ok' : 'warn'}`} aria-hidden="true" /><span className="dash-files-label">{backups.primary.label}</span></span>
                <span className="om-hint">{backups.primary.kind} · hourly{backups.lastPrimaryCopyAt ? ` · last copy of Files ${clock(backups.lastPrimaryCopyAt, hub.now)}` : ' · no copy of Files yet'}</span>
              </li>
              {backups.others.map((d) => (
                <li key={d.id} className="dash-files-disk">
                  <span className="dash-files-row"><span className="dash-files-dot dash-files-dot-muted" aria-hidden="true" /><span className="dash-files-label">{d.label}</span></span>
                  <span className="om-hint">{d.kind} · daily · not counted</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {away.length > 0 && (
        <>
          <h2 className="dash-files-head">Not reachable</h2>
          <ul className="dash-files-list" aria-label="Machines not reachable">
            {away.map((n) => (
              <li key={n.node_id} className="dash-files-disk">
                <span className="dash-files-row"><span className="dash-files-dot dash-files-dot-muted" aria-hidden="true" /><span className="dash-files-label">{n.hostname}</span></span>
                <span className="om-hint">Last seen {formatAgo(secondsSince(n.last_seen, hub.now))}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </nav>
  );
}

/** The Copies column header; absent when this person may not read the backup status. */
export function CopiesHeader() {
  return useContext(Ctx) ? <th scope="col">Copies</th> : null;
}

export function CopiesCell({ entry }: { entry: { type: string; mtime: string } }) {
  const s = useContext(Ctx);
  const { now } = useHub();
  const c = copiesOf(entry, s);
  if (!c) return null;
  if (c.kind === 'folder') return <td><span className="om-visually-hidden">Not counted for folders</span></td>;
  const tone = c.kind === 'copied' ? 'ok' : 'warn';
  return <td><span className="dash-files-copies"><span className={`dash-files-dot dash-files-dot-${tone}`} aria-hidden="true" />{copiesLabel(c, now)}{c.kind === 'copied' && <span className="om-visually-hidden">: on this box and on {c.primary}</span>}</span></td>;
}

/** "8 items · 6 have 2 copies · 2 wait for the copy at 02:10 · also copied to: NAS (daily)". Not a live region: it re-renders on every refresh. */
export function CopiesFooter({ entries }: { entries: Array<{ type: string; mtime: string; size: number | null }> }) {
  const s = useContext(Ctx);
  const { now } = useHub();
  const sum = copiesSummary(entries, s);
  const bytes = entries.reduce((n, e) => n + (e.type === 'dir' ? 0 : e.size ?? 0), 0);
  return (
    <p className="dash-files-foot">
      <strong>{entries.length} {entries.length === 1 ? 'item' : 'items'}</strong>{bytes ? ` · ${human(bytes)}` : ''}
      {sum && sum.copied > 0 && <span><span className="dash-files-dot dash-files-dot-ok" aria-hidden="true" /> {sum.copied} {sum.copied === 1 ? 'has' : 'have'} 2 copies</span>}
      {sum && sum.waiting > 0 && <span><span className="dash-files-dot dash-files-dot-warn" aria-hidden="true" /> {sum.waiting} {sum.waiting === 1 ? 'waits' : 'wait'} for {sum.next ? `the copy at ${clock(sum.next, now)}` : 'a backup destination'}</span>}
      {s && s.others.length > 0 && <span>Also copied to: {s.others.map((d) => `${d.label} (daily)`).join(', ')}</span>}
    </p>
  );
}

/** Drop files to upload them here; the same tus upload as the Upload button. */
export function FilesDropZone({ onFiles, busy }: { onFiles: (files: FileList) => void; busy: boolean }) {
  const [over, setOver] = useState(false);
  const stop = (e: DragEvent) => { e.preventDefault(); e.stopPropagation(); };
  return (
    <div
      className={over ? 'dash-files-drop dash-files-drop-over' : 'dash-files-drop'}
      onDragOver={(e) => { stop(e); if (!busy) setOver(true); }}
      onDragLeave={(e) => { stop(e); setOver(false); }}
      onDrop={(e) => { stop(e); setOver(false); if (!busy && e.dataTransfer.files.length) onFiles(e.dataTransfer.files); }}
      aria-label="Drop files here to upload them to this folder"
      role="region"
    >
      <Icon name="plus" size={18} /> {busy ? 'Uploading…' : 'Drop files here to upload them to this folder.'}
    </div>
  );
}
