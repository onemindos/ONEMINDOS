// SPDX-License-Identifier: Apache-2.0
// Backup read responses are unconstrained in OpenAPI: validate JSON, never invent API interfaces.
import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, uuid4, type components } from '@onemind/sdk';
import { Button, Card, Dialog, EmptyState, PageHeader, StatusPill } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load } from './parts';

type PendingBackup = { key: string; body: components['schemas']['RunBody'] };
// In-tab navigation must not turn a lost reply into a second logical request. No tokens here.
const pendingBackups = new Map<string, PendingBackup | undefined>();

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('The hub returned an invalid backup record.');
  return value as Record<string, unknown>;
}
function rows(value: unknown) {
  if (!Array.isArray(value)) throw new Error('The hub returned an invalid backup list.');
  return value.map(object);
}
function text(value: unknown, absent = 'Not reported') { return typeof value === 'string' && value ? value : absent; }
function backupStatus(value: unknown) {
  try {
    const s = object(value);
    if (typeof s.health !== 'string' || typeof object(object(s.badges).box).state !== 'string') throw new Error();
    return s;
  } catch { throw new Error('The hub returned an invalid backup status.'); }
}
async function read(sdk: OneMind, path: string) {
  try { return await sdk.call<unknown>({ method: 'GET', path }); }
  catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}

export function Backups() {
  const { token, person, mock } = useSignedIn();
  if (mock)
    return (
      <>
        <PageHeader title="Backups" />
        <div className="om-empty-fit">
          <EmptyState icon="backups" title="No backup proved yet" action={<Button disabled aria-describedby="backups-demo-note">Set up backups</Button>}>
            <p>A proven backup is one we restored in a test with restic and checked against its signature. Until one passes, nothing here says your data is safe.</p>
            <p id="backups-demo-note" role="status">Connect to a real hub to view backups. Demo mode has no backup data.</p>
          </EmptyState>
        </div>
      </>
    );
  return <LiveBackups key={person} token={token} person={person} />;
}
function LiveBackups({ token, person }: { token: string; person: string }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const status = usePoll(async () => backupStatus(await read(sdk, '/v1/backups/status')), 30_000);
  const targets = usePoll(async () => rows(await read(sdk, '/v1/backups/destinations')), 30_000);
  const runs = usePoll(async () => rows(await read(sdk, '/v1/backups/runs')), 15_000);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [expired, setExpired] = useState(false);
  const sending = useRef(false);
  const attempt = useRef(pendingBackups.get(person));
  const [receipt, setReceipt] = useState<{ id: string; state: string }>();
  const [error, setError] = useState(attempt.current ? 'An earlier reply was not confirmed. Retry the same request; it may already have been filed.' : '');
  const send = async () => {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError('');
    const pending = attempt.current ??= { key: uuid4(), body: { scope: 'box', approve: false, expires_at: new Date(sdk.hubNow() + 24 * 60 * 60 * 1000).toISOString() } };
    pendingBackups.set(person, pending);
    const client = new OneMind({ baseUrl: sdk.baseUrl, token, retries: 1, fetch: (url, init) => {
      const headers = new Headers(init?.headers);
      headers.set('Idempotency-Key', pending.key);
      return fetch(url, { ...init, headers });
    } });
    try {
      const action = object(await client.call<unknown>({ method: 'POST', path: '/v1/backups/runs', body: pending.body }));
      if (typeof action.id !== 'string' || !action.id.trim() || action.type !== 'backup.run'
        || action.idempotency_key !== pending.key || object(action.params).scope !== 'box'
        || typeof action.expires_at !== 'string' || Date.parse(action.expires_at) !== Date.parse(pending.body.expires_at ?? '')
        || typeof action.state !== 'string' || !['requested', 'awaiting_approval', 'accepted', 'dispatched', 'succeeded', 'failed', 'cancelled', 'expired', 'outcome_unknown'].includes(action.state)) {
        throw new Error('The hub returned an incomplete or mismatched request reply');
      }
      setReceipt({ id: action.id, state: action.state });
      attempt.current = undefined; setOpen(false);
      pendingBackups.set(person, undefined);
    } catch (e) {
      if (e instanceof OneMindError && e.status === 409 && e.code === 'expired') {
        // The gateway replays existing keys before testing expiry. This refusal confirms
        // the old body cannot create a request. Never rotate identity on a lost reply.
        attempt.current = undefined;
        pendingBackups.set(person, undefined);
        setExpired(true);
        setError('The gateway confirmed the old request has expired. You may explicitly start a new request.');
      } else setError(`${e instanceof Error ? e.message : String(e)}. Retry the same request; it may already have been filed.`);
    }
    finally { sending.current = false; setBusy(false); }
  };
  const refresh = () => { void status.reload(); void targets.reload(); void runs.reload(); };
  return <div className="dash-stack">
    <PageHeader title="Backups" lede="Backup health and destinations reported by your hub." />
    <Button variant="secondary" onClick={refresh}>Refresh backups</Button>
    <Button onClick={() => setOpen(true)}>Request backup</Button>
    {receipt && <p role="status">Request {receipt.id}: {receipt.state}. No approval was sent. <Link to={href.approval(receipt.id)}>Open request in Approvals</Link></p>}
    <Dialog role="alertdialog" open={open} onClose={() => { if (!busy) setOpen(false); }} title="Request a whole-box backup" description="Nothing runs until the owner approves. This files a request for the configured backup destination, not an approval." actions={expired
      ? <Button onClick={() => { setExpired(false); setError(''); }}>Start a new request</Button>
      : <Button disabled={busy} onClick={() => void send()}>{busy ? 'Sending request…' : error ? 'Retry same request' : 'Send request'}</Button>}>
      <p>Scope: whole box. The gateway checks setup and backup permissions.</p>
      {error && <p role="alert">{error}</p>}
    </Dialog>
    {[status, targets, runs].some((r) => r.error && r.data !== undefined) && <p role="status">Could not refresh. Showing previously fetched backup data; refresh to check again.</p>}
    <Load res={status} what="Loading backup health">{(s) => <Card as="article" title="Backup health" variant="sunken">
      <StatusPill tone="neutral" label={text(s.health)} />
      {typeof s.reason === 'string' && <p>{s.reason}</p>}
      <dl className="om-facts">
        <div><dt>Last successful backup</dt><dd>{text(s.last_success_at, 'No successful run reported')}</dd></div>
        <div><dt>Most recent verified restore</dt><dd>{text(s.last_verified_restore_at, 'Not verified')}</dd></div>
        <div><dt>Next run</dt><dd>{text(s.next_run_at, 'Not scheduled')}</dd></div>
        <div><dt>Box protection</dt><dd>{text(object(object(s.badges).box).state)}</dd></div>
      </dl>
    </Card>}</Load>
    <Load res={targets} what="Loading backup destinations">{(items) => <Card title="Backup destinations">
      {items.length === 0 ? <p>No backup destinations configured.</p> : <ul>{items.map((d) => <li key={text(d.id)}><strong>{text(d.label)}</strong> — {text(d.kind)}{d.primary === true ? ' · primary' : ''}{d.append_only === true ? ' · append-only' : ''}</li>)}</ul>}
    </Card>}</Load>
    <Load res={runs} what="Loading backup runs">{(items) => <Card title="Backup runs">
      {items.length === 0 ? <p>No backup runs reported.</p> : <ul>{items.map((r) => <li key={text(r.id)}><strong>{text(r.id)}</strong> — {text(r.state)}{typeof r.finished_at === 'string' ? ` · finished ${r.finished_at}` : ''}{typeof r.error === 'string' ? ` · ${r.error}` : ''}</li>)}</ul>}
    </Card>}</Load>
  </div>;
}
