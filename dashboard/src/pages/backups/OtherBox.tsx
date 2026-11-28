// SPDX-License-Identifier: Apache-2.0
// Backups > Restore from another box (UMB-P08, owner only): bring one app's data back from the backup of a dead or
// replaced box. POST /v1/onboarding/restore/candidates lists what a destination holds (read only); POST
// /v1/onboarding/restore/apps files the ordinary `backup.restore` request, never approved here: it waits in Approvals.
// The recovery key from the kit opens the old box's backup. It lives in this form's memory only, is sent once per call,
// is never put in a URL, storage or log, and is cleared as soon as a request is filed. The CLI twin is
// `onemind box-restore`.
import { useRef, useState } from 'react';
import { Link } from 'react-router';
import { OneMindError, uuid4, type OneMind, type components } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { useSignedIn } from '../../session';
import { href } from '../../shell/routes';
import { TextField } from '../parts';
import { object } from './shared';

type CandidatesBody = components['schemas']['RestoreCandidatesBody'];
type CandidatesView = components['schemas']['RestoreCandidatesView'];
type RestorePoint = components['schemas']['RestorePoint'];
type AppBody = components['schemas']['RestoreAppBody'];
/** A point this form can restore from: one with a run id (a point without one holds no app data to pick). */
type Point = RestorePoint & { run_id: string };

function points(v: CandidatesView): Point[] {
  if (!v || !Array.isArray(v.points)) throw new Error('The hub returned an invalid list of restore points.');
  return v.points.filter((p): p is Point => typeof p.run_id === 'string' && p.run_id !== '' && Array.isArray(p.apps));
}
const takenAt = (p: RestorePoint) => p.taken_at ?? 'unknown time';
const why = (e: unknown) => (e instanceof OneMindError ? (e.status === 403 ? 'Only the owner can do this.' : e.message) : e instanceof Error ? e.message : String(e));

export function OtherBoxRestore({ sdk, destinations }: { sdk: OneMind; destinations: { id: string; label: string }[] }) {
  const { principal } = useSignedIn();
  const [dest, setDest] = useState('');
  const [box, setBox] = useState('');
  const [key, setKey] = useState('');
  const [found, setFound] = useState<Point[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState<{ id: string; app: string }>();
  const attempt = useRef<{ sig: string; key: string } | undefined>(undefined);
  if (principal?.role !== 'owner') return null;
  const destination = dest || destinations[0]?.id || '';
  const ready = !!destination && !!box.trim() && key.trim().length >= 32;
  const look = async () => {
    setBusy(true); setError(''); setFound(undefined); setReceipt(undefined);
    const body: CandidatesBody = { destination_id: destination, box_id: box.trim(), recovery_key: key.trim() };
    try { setFound(points(await sdk.call<CandidatesView>({ method: 'POST', path: '/v1/onboarding/restore/candidates', body }))); }
    catch (e) { setError(why(e)); }
    finally { setBusy(false); }
  };
  const restore = async (p: Point, app: string) => {
    setBusy(true); setError('');
    const sig = `${destination}|${box}|${p.run_id}|${app}`;
    if (attempt.current?.sig !== sig) attempt.current = { sig, key: uuid4() };
    const body: AppBody = { destination_id: destination, box_id: box.trim(), recovery_key: key.trim(), run_id: p.run_id, app_id: app, approve: false };
    try {
      // The 202 reply is the filed action; the spec leaves it untyped, so only its id is read and checked.
      const r = object(await sdk.call<unknown>({ method: 'POST', path: '/v1/onboarding/restore/apps', body, headers: { 'Idempotency-Key': attempt.current.key } }));
      if (typeof r.id !== 'string' || !r.id) throw new Error('The hub returned an incomplete reply.');
      setReceipt({ id: r.id, app }); setKey(''); setFound(undefined); attempt.current = undefined;
    } catch (e) { setError(`${why(e)}. If this was a lost reply, try the same button again: it will not file a second request.`); }
    finally { setBusy(false); }
  };
  return (
    <Card as="section" title="Restore an app from another box’s backup">
      <p>
        Use this after moving to new hardware. Install the app first, then bring its data back from the old box’s backup. You need the box ID and the recovery key from the old box’s recovery kit. Nothing is restored until you approve it in Approvals.
      </p>
      {destinations.length === 0 ? <p className="om-hint">Add a backup destination first (a USB disk, another box or an off-site bucket).</p> : (
        <form onSubmit={(e) => { e.preventDefault(); if (ready && !busy) void look(); }} aria-label="Find restore points">
          <label htmlFor="ob-dest">Where the backup is</label>
          <select id="ob-dest" value={destination} onChange={(e) => setDest(e.target.value)}>
            {destinations.map((d) => <option key={d.id} value={d.id}>Backup on {d.label}</option>)}
          </select>
          <TextField id="ob-box" label="Old box ID" value={box} onChange={setBox} />
          <TextField id="ob-key" label="Recovery key (from the kit)" value={key} onChange={setKey} type="password" autoComplete="off" />
          <Button type="submit" disabled={!ready || busy}>Look for restore points</Button>
        </form>
      )}
      {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
      {receipt && <p role="status">Request {receipt.id} to restore {receipt.app} was filed and is not approved. <Link to={href.approval(receipt.id)}>Review it in Approvals</Link>. Approve it soon: the box keeps the recovery key in memory only, so if the box restarts before you approve, the request cannot run and you file it again with the key.</p>}
      {found && (found.length === 0 ? <p role="status">That backup holds no restore points for this key.</p> : (
        <ul aria-label="Restore points">
          {found.map((p) => (
            <li key={p.run_id}>
              <strong>{takenAt(p)}</strong>
              {p.apps.length === 0 ? <span className="om-hint"> · no app data (box files only)</span> : p.apps.map((a) => (
                <span key={a}> <Button size="sm" variant="secondary" disabled={busy} onClick={() => void restore(p, a)} aria-label={`Restore ${a} from ${takenAt(p)}`}>Restore {a}…</Button></span>
              ))}
            </li>
          ))}
        </ul>
      ))}
    </Card>
  );
}
