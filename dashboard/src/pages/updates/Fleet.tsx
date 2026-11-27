// SPDX-License-Identifier: Apache-2.0
// The fleet: which OS version every machine runs (GET /v1/os/fleet) and the staged rollouts
// (GET /v1/os/rollouts). Starting or resuming a rollout only FILES a request in Approvals: nothing is
// offered to any machine until an owner approves it. Cancelling stops offering the version to more
// machines (owner only); machines already updated stay updated.
import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { usePoll } from '../../lib/hooks';
import { uuidv4 } from '../../lib/uuid';
import { useSignedIn } from '../../session';
import { useShell } from '../../shell/Shell';
import { href } from '../../shell/routes';
import { Load } from '../parts';
import { getJson, record, records, str } from '../records';

const VERSION = /^[0-9]{1,10}(\.[0-9]{1,20}){0,5}(-dev)?$/;
const ACTIVE = ['running', 'paused'];
const STATE_WORDS: Record<string, string> = { running: 'Running', paused: 'Paused: needs a decision', completed: 'Finished', cancelled: 'Cancelled' };
/** "3 machines": the fleet's count is a number, never a string. */
const machines = (n: unknown) => (typeof n === 'number' ? `${n} ${n === 1 ? 'machine' : 'machines'}` : 'an unknown number of machines');
const stage = (r: Record<string, unknown>) => `wave ${(typeof r.stage === 'number' ? r.stage : 0) + 1} of ${Array.isArray(r.stages) ? r.stages.length : '?'}`;

export function Fleet() {
  const { token, person, mock } = useSignedIn();
  const { role } = useShell(); // a real hub's session has no principal; the role comes from GET /v1/me
  if (mock) return null;
  return <LiveFleet key={person} token={token} owner={role === 'owner'} />;
}

function LiveFleet({ token, owner }: { token: string; owner: boolean }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const fleet = usePoll(async () => { const f = record(await getJson(sdk, '/v1/os/fleet')); return { machines: records(f.machines), versions: records(f.versions) }; }, 30_000);
  const rollouts = usePoll(async () => records(await getJson(sdk, '/v1/os/rollouts')), 30_000);
  const [version, setVersion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filed, setFiled] = useState<{ id: string; what: string }>();
  const [cancelling, setCancelling] = useState<string>();
  const key = useRef<{ sig: string; key: string } | undefined>(undefined);
  // One idempotency key per exact request, kept until it succeeds, so a lost reply is never two requests.
  const file = async (type: 'os.rollout.start' | 'os.rollout.resume', params: Record<string, unknown>, what: string) => {
    if (busy) return;
    setBusy(true); setError('');
    const sig = type + JSON.stringify(params);
    if (key.current?.sig !== sig) key.current = { sig, key: uuidv4() };
    try {
      const a = record(await sdk.call<unknown>({ method: 'POST', path: '/v1/actions', body: { type, params, idempotency_key: key.current.key, expires_at: new Date(sdk.hubNow() + 24 * 3600_000).toISOString() } }));
      if (typeof a.id !== 'string' || a.type !== type) throw new Error('The hub sent back a reply this page does not understand');
      key.current = undefined; setFiled({ id: a.id, what });
    } catch (e) {
      setError(e instanceof OneMindError && e.status === 409 ? e.message : `${e instanceof Error ? e.message : String(e)}. Try again; the request may already have been filed.`);
    } finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!cancelling || busy) return;
    setBusy(true); setError('');
    try { await sdk.call<unknown>({ method: 'POST', path: `/v1/os/rollouts/${encodeURIComponent(cancelling)}/cancel` }); setCancelling(undefined); await rollouts.reload(); await fleet.reload(); }
    catch (e) { setError(e instanceof OneMindError && e.status === 403 ? 'Only an owner can cancel a rollout.' : e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const active = rollouts.data?.some((r) => ACTIVE.includes(str(r.state, '')));
  return <section aria-label="Fleet" className="dash-stack">
    <Load res={fleet} what="Loading the fleet">{(f) => <Card title="Every machine and its version">
      {f.machines.length === 0 ? <p>No machines have reported yet.</p> : <ul>{f.machines.map((m) => <li key={str(m.node_id)}>
        <strong>{str(m.hostname, str(m.node_id))}</strong> · {str(m.board, 'unknown board')} · <StatusPill tone={m.status === 'online' ? 'ok' : 'neutral'} label={str(m.status, 'unknown')} />
        <dl className="om-facts">
          <div><dt>Version</dt><dd>{str(m.version, m.updatable === false ? 'Does not report updates' : 'Not reported')}</dd></div>
          <div><dt>Update</dt><dd>{str(m.update_state, 'Idle')}</dd></div>
          {typeof m.available_version === 'string' && <div><dt>On offer</dt><dd>{m.available_version}</dd></div>}
        </dl>
      </li>)}</ul>}
      {f.versions.length > 0 && <p className="om-note">Versions in use: {f.versions.map((v) => `${str(v.version)} on ${machines(v.count)}`).join(', ')}.</p>}
    </Card>}</Load>
    <Load res={rollouts} what="Loading rollouts">{(items) => <Card title="Rollouts to the whole fleet">
      <p className="om-note">A rollout offers a new version to a few machines first, waits until each one is healthy, then offers it to the next wave. Nothing is offered until an owner approves the request.</p>
      {items.length === 0 ? <p>No rollouts yet.</p> : <ul>{items.map((r) => {
        const id = str(r.id, ''); const state = str(r.state, '');
        const c = record(r.counts ?? {});
        return <li key={id}>
          <strong>{str(r.version)}</strong> · {STATE_WORDS[state] ?? state} · {stage(r)}
          <dl className="om-facts">
            <div><dt>Machines</dt><dd>{[['waiting', 'waiting'], ['offered', 'offered'], ['succeeded', 'done'], ['failed', 'failed']].map(([k, w]) => `${typeof c[k!] === 'number' ? c[k!] : 0} ${w}`).join(', ')}</dd></div>
            {typeof r.reason === 'string' && r.reason && <div><dt>Why</dt><dd>{r.reason}</dd></div>}
          </dl>
          {owner && state === 'paused' && <Button size="sm" variant="secondary" disabled={busy} onClick={() => void file('os.rollout.resume', { rollout_id: id }, `Resume ${str(r.version)}`)}>Ask to resume</Button>}
          {owner && ACTIVE.includes(state) && <Button size="sm" variant="secondary" disabled={busy} onClick={() => { setError(''); setCancelling(id); }}>Cancel rollout</Button>}
        </li>;
      })}</ul>}
      {owner && !active && <form onSubmit={(e) => { e.preventDefault(); if (VERSION.test(version.trim())) void file('os.rollout.start', { version: version.trim() }, `Roll out ${version.trim()}`); }}>
        <label htmlFor="rollout-version">Version to roll out</label>{' '}
        <input id="rollout-version" className="om-input" value={version} onChange={(e) => setVersion(e.target.value)} placeholder="for example 1.3.0" autoComplete="off" />{' '}
        <Button type="submit" disabled={busy || !VERSION.test(version.trim())}>Ask to start a rollout</Button>
        <p className="om-note">Default waves: 10 %, then 50 %, then everyone. It pauses on the first machine that fails.</p>
      </form>}
      {filed && <p role="status">{filed.what}: waiting for an owner. <Link to={href.approval(filed.id)}>Open it in Approvals</Link></p>}
      {error && !cancelling && <p role="alert" className="om-note om-tone-bad">{error}</p>}
    </Card>}</Load>
    <Dialog open={!!cancelling} role="alertdialog" title="Cancel this rollout?" onClose={() => { if (!busy) setCancelling(undefined); }} actions={<Button disabled={busy} onClick={() => void cancel()}>{busy ? 'Cancelling…' : 'Yes, cancel the rollout'}</Button>}>
      <p>No more machines will be offered this version. Machines that already updated stay updated.</p>
      {error && <p role="alert">{error}</p>}
    </Dialog>
  </section>;
}
