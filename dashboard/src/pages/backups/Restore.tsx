// SPDX-License-Identifier: Apache-2.0
// Snapshot browser and restore wizard (UI sprint P0, #141/#145). Restoring is an approval request:
// the wizard files `POST /v1/restores` unapproved, shows the plan the hub computed (what returns, what
// stops, the undo snapshot), and sends the owner to Approvals, where the approval is decided (with a
// fresh passkey where the gateway asks for it). Nothing here approves anything.
import { useState } from 'react';
import { Link } from 'react-router';
import type { OneMind } from '@onemind/sdk';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { usePoll } from '../../lib/hooks';
import { href } from '../../shell/routes';
import { Load } from '../parts';
import { object, read, rows, strings, text, useFiling } from './shared';

interface Snap { id: string; short: string; unit: string; appId: string | undefined; takenAt: string; reason: string; paths: string[]; verifiedAt: string | undefined }
function snap(r: Record<string, unknown>): Snap {
  if (typeof r.id !== 'string' || !r.id) throw new Error('The hub returned an invalid snapshot.');
  return { id: r.id, short: text(r.short_id, r.id.slice(0, 8)), unit: text(r.unit, 'unknown'), appId: typeof r.app_id === 'string' && r.app_id ? r.app_id : undefined,
    takenAt: text(r.taken_at, 'unknown time'), reason: text(r.reason, ''), paths: strings(r.paths), verifiedAt: typeof r.verified_at === 'string' ? r.verified_at : undefined };
}
const folderOk = (path: string, paths: string[]) => paths.some((p) => path === p || path.startsWith(p.replace(/\/+$/, '') + '/'))
  && !path.split('/').slice(1).some((s) => s === '' || s === '.' || s === '..') ;

export function RestoreSection({ sdk, token }: { sdk: OneMind; token: string }) {
  const snaps = usePoll(async () => rows(await read(sdk, '/v1/backups/snapshots')).map(snap), 30_000);
  const restores = usePoll(async () => rows(await read(sdk, '/v1/restores')), 15_000);
  const [pick, setPick] = useState<Snap>();
  return <>
    <Load res={snaps} what="Loading restore points">{(items) => <Card title="Restore points">
      {items.length === 0 ? <p>No restore points yet. They appear after the first backup run; add a backup destination first if you have none.</p> : <ul>{items.map((s) => <li key={s.id}>
        <strong>{s.appId ?? s.unit}</strong> · {s.takenAt}{s.reason ? ` · ${s.reason}` : ''} · {s.verifiedAt ? `verified ${s.verifiedAt}` : 'not verified'}{' '}
        {s.appId
          ? <Button size="sm" variant="secondary" onClick={() => setPick(s)} aria-label={`Restore ${s.appId} from ${s.takenAt}`}>Restore…</Button>
          : <span className="om-hint">A whole-box restore runs when you set up a fresh box.</span>}
      </li>)}</ul>}
    </Card>}</Load>
    <Load res={restores} what="Loading restores">{(items) => items.length > 0 && <Card title="Restores">
      <ul>{items.map((r) => <li key={text(r.id)}>
        <strong>{text(object(r.plan).summary, text(r.id))}</strong> — <StatusPill tone="neutral" label={text(r.state)} />
        {typeof r.pre_restore_snapshot_id === 'string' && <> · undo snapshot <code>{r.pre_restore_snapshot_id.slice(0, 8)}</code></>}
        {typeof r.error === 'string' && <> · {r.error}</>}
        {typeof r.action_id === 'string' && r.state === 'awaiting_approval' && <> · <Link to={href.approval(r.action_id)}>Approve in Approvals</Link></>}
      </li>)}</ul>
    </Card>}</Load>
    {pick && <Wizard key={pick.id} sdk={sdk} token={token} snap={pick} onClose={() => { setPick(undefined); void restores.reload(); }} />}
  </>;
}

function Wizard({ sdk, token, snap: s, onClose }: { sdk: OneMind; token: string; snap: Snap; onClose: () => void }) {
  const { file, busy, error } = useFiling(sdk, token);
  const [whole, setWhole] = useState(true);
  const [path, setPath] = useState(s.paths[0] ?? '');
  const [filed, setFiled] = useState<{ id: string; restore: Record<string, unknown> | undefined }>();
  const bad = !whole && !folderOk(path, s.paths);
  const scope = whole ? { app_id: s.appId } : { app_id: s.appId, path };
  const send = async () => {
    const r = await file('/v1/restores', 'backup.restore', { snapshot_id: s.id, scope, mode: 'portable', target: 'in_place' });
    if (r) setFiled({ id: r.id, restore: r.body.restore && typeof r.body.restore === 'object' ? object(r.body.restore) : undefined });
  };
  const plan = filed?.restore ? object(filed.restore.plan) : undefined;
  return <Dialog role="alertdialog" open onClose={() => { if (!busy) onClose(); }} title={`Restore ${s.appId}`}
    description="Nothing is restored until the owner approves the request in Approvals."
    actions={filed ? <><Link to={href.approval(filed.id)}>Open request in Approvals</Link><Button variant="secondary" onClick={onClose}>Close</Button></>
      : <><Button variant="secondary" disabled={busy} onClick={onClose}>Cancel</Button><Button disabled={busy || bad} onClick={() => void send()}>{busy ? 'Sending request…' : error ? 'Retry same request' : 'File restore request'}</Button></>}>
    {!filed ? <>
      <p>Step 1 of 2: choose what comes back. Restore point <code>{s.short}</code> of {s.appId}, taken {s.takenAt}.</p>
      <fieldset>
        <legend>What to restore</legend>
        <label><input type="radio" name="restore-scope" checked={whole} onChange={() => setWhole(true)} /> The whole app: all {s.paths.length} saved folder(s) and its database if it has one</label>
        <label><input type="radio" name="restore-scope" checked={!whole} disabled={s.paths.length === 0} onChange={() => setWhole(false)} /> One folder only</label>
      </fieldset>
      {!whole && <>
        <label htmlFor="restore-path">Folder to put back</label>
        <input id="restore-path" list="restore-paths" value={path} onChange={(e) => setPath(e.target.value)} />
        <datalist id="restore-paths">{s.paths.map((p) => <option key={p} value={p} />)}</datalist>
        {bad && <p role="alert">The folder must be an absolute path inside this restore point.</p>}
      </>}
      <p>Mode: portable, restored in place. Today's data is saved first so the restore can be undone.</p>
      {error && <p role="alert">{error}</p>}
    </> : <>
      <p role="status">Step 2 of 2: request filed ({filed.id}). The hub's plan, to review before you approve it:</p>
      {plan ? <>
        <p><strong>{text(plan.summary)}</strong></p>
        <ol>{strings(plan.steps).map((st) => <li key={st}>{st}</li>)}</ol>
        <p>Downtime: {text(plan.downtime, 'not stated')}.</p>
        {strings(plan.warnings).map((w) => <p key={w} className="om-note om-tone-warn">{w}</p>)}
      </> : <p>The hub did not return a plan. Check the request in Approvals before approving it.</p>}
      <p>The undo snapshot is taken at the start of the restore; its id shows in Restores once it runs. If the app does not come back healthy, today's data is put back automatically.</p>
      <p>Open the request in Approvals to approve it. Approving can ask for a fresh passkey.</p>
    </>}
  </Dialog>;
}
