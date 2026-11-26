// SPDX-License-Identifier: Apache-2.0
// Changing the disks: the five mirror actions (start a mirror, add a disk, replace a member, take a
// member out, repair) as a two-step flow. Step 1 asks the box for the plan (POST /v1/storage/plans,
// a dry run that changes nothing) and shows which disks would be written, the safety checks and the
// warnings. Step 2 files the request (POST /v1/storage/actions); the owner decides in Approvals, where
// a destructive action needs their passkey. Nothing is changed from this page.
import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, StatusPill } from '@onemind/ui';
import { uuidv4 } from '../../lib/uuid';
import { useSignedIn } from '../../session';
import { href } from '../../shell/routes';
import { record, records, str } from '../records';

type PlanRequest = components['schemas']['StoragePlanRequest'];
type ActionType = PlanRequest['type'];
type Params = components['schemas']['StorageParams'];
const ACTIONS: readonly { type: ActionType; label: string; needs: readonly ('device' | 'member')[]; destructive: boolean }[] = [
  { type: 'storage.mirror.create', label: 'Start a mirror with a blank disk', needs: ['device'], destructive: true },
  { type: 'storage.mirror.add', label: 'Add a blank disk to the mirror', needs: ['device'], destructive: true },
  { type: 'storage.mirror.replace', label: 'Replace a member with a blank disk', needs: ['member', 'device'], destructive: true },
  { type: 'storage.mirror.remove', label: 'Take a member out of the mirror', needs: ['member'], destructive: true },
  { type: 'storage.mirror.repair', label: 'Repair the mirror', needs: [], destructive: false },
];
/** The two options the API takes (StorageParams): wipe on replace and remove, unprotect on remove only. */
const WIPES: ActionType[] = ['storage.mirror.replace', 'storage.mirror.remove'];
/**
 * A disk size the way a person reads a disk label: decimal units, TB from 1000 GB up, at most one
 * decimal and no trailing ".0" (256 GB, 1.5 TB, 4 TB). The CLI's storageSize uses the same rule.
 */
export function diskSize(v: unknown): string {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) return 'size not reported';
  const round = (n: number) => Math.round(n * 10) / 10;
  return round(v / 1e9) >= 1000 ? `${round(v / 1e12)} TB` : `${round(v / 1e9)} GB`;
}
const gb = diskSize;

interface Plan { type: ActionType; hash: string; blocked: boolean; encrypted: boolean; targets: Record<string, unknown>[]; checks: Record<string, unknown>[]; warnings: string[]; steps: number }
function plan(value: unknown): Plan {
  const body = record(value);
  const p = record(body.plan);
  return { type: body.type as ActionType, hash: str(body.plan_sha256, ''), blocked: p.blocked === true, encrypted: p.encrypted === true,
    targets: Array.isArray(p.targets) ? records(p.targets) : [], checks: Array.isArray(p.checks) ? records(p.checks) : [],
    warnings: Array.isArray(p.warnings) ? p.warnings.filter((w): w is string => typeof w === 'string') : [], steps: Array.isArray(p.steps) ? p.steps.length : 0 };
}
function why(e: unknown): string {
  if (e instanceof OneMindError) {
    if (e.status === 403) return 'Only an owner can change the disks.';
    if (e.status === 422) return 'That choice is not complete. Pick every disk the action needs.';
    if (e.status === 409) return `The box refused it: ${e.message}`;
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

/** The page already polls the summary and the disks: they come in as props so this adds no requests. */
export function StorageChanges({ summary, disks }: { summary: Record<string, unknown> | undefined; disks: Record<string, unknown>[] | undefined }) {
  const { token, person, mock, principal } = useSignedIn();
  if (mock) return null;
  return <LiveChanges key={person} token={token} owner={principal?.role === 'owner'} summary={summary} disks={disks} />;
}

function LiveChanges({ token, owner, summary: s, disks: all }: { token: string; owner: boolean; summary: Record<string, unknown> | undefined; disks: Record<string, unknown>[] | undefined }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const members = Array.isArray(s?.members) ? records(s.members) : [];
  const on = s?.enabled === true && s.available === true;
  const [type, setType] = useState<ActionType>('storage.mirror.create');
  const [device, setDevice] = useState('');
  const [member, setMember] = useState('');
  const [unprotect, setUnprotect] = useState(false);
  const [wipe, setWipe] = useState(false);
  const [shown, setShown] = useState<Plan>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filed, setFiled] = useState<string>();
  const key = useRef<{ sig: string; key: string } | undefined>(undefined);
  const blank = (all ?? []).filter((d) => d.role === 'unused'); // the only role a plan may wipe
  const spec = ACTIONS.find((a) => a.type === type)!;
  const canWipe = WIPES.includes(type);
  const canUnprotect = type === 'storage.mirror.remove';
  const params = (): Params => ({ ...(spec.needs.includes('device') ? { device } : {}), ...(spec.needs.includes('member') ? { member } : {}),
    unprotect: canUnprotect && unprotect, wipe: canWipe && wipe });
  const ready = spec.needs.every((n) => (n === 'device' ? device : member));
  const reset = () => { setShown(undefined); setFiled(undefined); setError(''); };
  const preview = async () => {
    if (!ready || busy) return;
    setBusy(true); reset();
    try { setShown(plan(await sdk.call<unknown>({ method: 'POST', path: '/v1/storage/plans', body: { type, params: params() } satisfies PlanRequest }))); }
    catch (e) { setError(why(e)); }
    finally { setBusy(false); }
  };
  const request = async () => {
    if (!shown || shown.blocked || busy) return;
    setBusy(true); setError('');
    const sig = type + JSON.stringify(params()) + shown.hash;
    if (key.current?.sig !== sig) key.current = { sig, key: uuidv4() };
    try {
      const r = record(await sdk.call<unknown>({ method: 'POST', path: '/v1/storage/actions', body: { type, params: params() } satisfies components['schemas']['StorageActionRequest'], headers: { 'Idempotency-Key': key.current.key } }));
      const id = str(record(r.action).id, '');
      if (!id) throw new Error('The box sent back a reply this page does not understand');
      key.current = undefined; setFiled(id);
    } catch (e) { setError(`${why(e)}${e instanceof OneMindError ? '' : ' Try again; the request may already have been filed.'}`); }
    finally { setBusy(false); }
  };
  if (!on) return null; // storage off or not answering: nothing to change, nothing to offer
  if (!owner) return <Card title="Change the disks"><p>Only an owner can change the disks.</p></Card>;
  return <Card title="Change the disks">
    <p className="om-note">Nothing changes when you look. You first see exactly what would happen, then ask for approval, and an owner approves in Approvals with their passkey. Disks you add must be blank: whatever is on them is erased.</p>
    <p><label htmlFor="stor-action">What do you want to do?</label>{' '}
      <select id="stor-action" className="om-input" value={type} onChange={(e) => { setType(e.target.value as ActionType); setUnprotect(false); setWipe(false); reset(); }}>{ACTIONS.map((a) => <option key={a.type} value={a.type}>{a.label}</option>)}</select></p>
    {spec.needs.includes('device') && <p><label htmlFor="stor-device">The blank disk</label>{' '}
      <select id="stor-device" className="om-input" value={device} onChange={(e) => { setDevice(e.target.value); reset(); }}>
        <option value="">Choose a disk</option>
        {blank.length === 0 && <option disabled value="">No blank disk found</option>}
        {blank.map((d) => <option key={str(d.path)} value={str(d.path, '')}>{str(d.model, str(d.path))} · {gb(d.size_bytes)} · {str(d.path)}</option>)}
      </select></p>}
    {spec.needs.includes('member') && <p><label htmlFor="stor-member">The member</label>{' '}
      <select id="stor-member" className="om-input" value={member} onChange={(e) => { setMember(e.target.value); reset(); }}>
        <option value="">Choose a member</option>
        {/* devid:N for every member, missing ones too: "missing" names only the one missing member, so two missing members would read the same. */}
        {members.map((m) => <option key={String(m.devid)} value={`devid:${String(m.devid)}`}>Member {String(m.devid)}{m.missing === true ? ' (missing)' : ''} · {gb(m.size_bytes)}</option>)}
      </select></p>}
    {canUnprotect && <p><label><input type="checkbox" aria-describedby="stor-unprotect-note" checked={unprotect} onChange={(e) => { setUnprotect(e.target.checked); reset(); }} />{' '}
      Allow the mirror to drop to one disk</label><br />
      <span id="stor-unprotect-note" className="om-note">Needed to take a member out of a two-disk mirror. Your data is then kept on one disk only, so a disk failure loses it until you add another disk.</span></p>}
    {canWipe && <p><label><input type="checkbox" aria-describedby="stor-wipe-note" checked={wipe} onChange={(e) => { setWipe(e.target.checked); reset(); }} />{' '}
      Erase the old disk afterwards</label><br />
      <span id="stor-wipe-note" className="om-note">Everything on the disk that leaves the mirror is erased, so it can be given away or reused. Leave this off to keep it as it is. A missing disk cannot be erased.</span></p>}
    <Button disabled={!ready || busy} onClick={() => void preview()}>{busy && !shown ? 'Checking…' : 'Show what would happen'}</Button>
    {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
    {shown && <section aria-label="Plan">
      <h3>What would happen</h3>
      {shown.blocked ? <p className="om-note om-tone-bad" role="status">The box will not do this: a safety check failed.</p> : <p role="status">The box can do this in {shown.steps} steps.{shown.encrypted ? ' The new disk is encrypted.' : ''}</p>}
      {shown.targets.length > 0 && <><p>These disks would be written to, and anything on them erased:</p><ul>{shown.targets.map((t) => <li key={str(t.path)}>{str(t.model, str(t.path))} · {gb(t.size_bytes)} · {str(t.path)}{typeof t.serial_tail === 'string' ? ` · serial ends ${t.serial_tail}` : ''}</li>)}</ul></>}
      <ul aria-label="Safety checks">{shown.checks.map((c) => <li key={str(c.id)}><StatusPill tone={c.ok === true ? 'ok' : 'bad'} label={c.ok === true ? 'Passed' : 'Failed'} dot={false} /> {str(c.detail, str(c.id))}</li>)}</ul>
      {shown.warnings.length > 0 && <ul aria-label="Warnings">{shown.warnings.map((w) => <li key={w} className="om-tone-warn">{w}</li>)}</ul>}
      {!filed && <Button disabled={shown.blocked || busy} onClick={() => void request()}>{busy ? 'Sending request…' : 'Ask for approval'}</Button>}
      {filed && <p role="status">Waiting for an owner. <Link to={href.approval(filed)}>Open it in Approvals</Link></p>}
    </section>}
  </Card>;
}
