// SPDX-License-Identifier: Apache-2.0
// OS updates (UMB-P05, #142): what each node runs, its A/B slots, the update on offer and the
// commit/rollback history, from GET /v1/os/updates[/history]. "Install" only files an
// os.update.install request; nothing installs until the owner approves it. "Go back" (P-16) files an
// os.rollback request the same way; the owner approves it with a passkey in Approvals. The update
// policy and window (REL-02, #154) are changed the same way: updates/OsSettings.tsx.
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
import { UpdatePolicy } from './UpdatePolicy';
import { Fleet } from './updates/Fleet';
import { OsSettings } from './updates/OsSettings';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load } from './parts';

type Rec = Record<string, unknown>;
function record(v: unknown, what: string): Rec {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error(`The hub returned an invalid ${what}.`);
  return v as Rec;
}
function list(v: unknown, what: string) {
  if (!Array.isArray(v)) throw new Error(`The hub returned an invalid ${what}.`);
  return v.map((x) => record(x, what));
}
function text(v: unknown, missing = 'Not reported') { return typeof v === 'string' && v ? v : missing; }
function apiError(e: unknown) {
  return e instanceof OneMindError ? new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason) : e;
}
async function call(client: OneMind, method: 'GET' | 'POST', path: string, body?: unknown) {
  try { return await client.call<unknown>({ method, path, body }); } catch (e) { throw apiError(e); }
}

export function Updates() {
  const { token, person, mock } = useSignedIn();
  return mock ? <><PageHeader title="OS updates" /><p role="status">Connect to a real hub to see OS updates. Demo mode has no update data.</p></> : <LiveUpdates key={person} token={token} />;
}

function LiveUpdates({ token }: { token: string }) {
  const { canDecide } = useSignedIn();
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const status = usePoll(async () => {
    const s = record(await call(client, 'GET', '/v1/os/updates'), 'update status');
    return { nodes: list(s.nodes, 'update status'), install: record(s.install, 'update status'), rollback: record(s.rollback ?? { available: false }, 'update status'),
      settings: record(s.settings ?? { available: false }, 'update status') };
  }, 30_000);
  const history = usePoll(async () => {
    const h = record(await call(client, 'GET', '/v1/os/updates/history'), 'update history');
    return { events: list(h.events, 'update history'), requests: list(h.requests, 'update history') };
  }, 30_000);
  const [filed, setFiled] = useState<{ id: string; state: string; what: string }>();
  const [failed, setFailed] = useState<string>();
  const [busy, setBusy] = useState(false);

  const request = async (type: 'os.update.install' | 'os.rollback', node: string, version: string) => {
    setBusy(true); setFailed(undefined);
    try {
      const a = record(await call(client, 'POST', '/v1/actions', {
        type, params: { node_id: node, version }, idempotency_key: uuidv4(),
        expires_at: new Date(Date.now() + 24 * 3600_000).toISOString(),
      }), 'action');
      if (typeof a.id !== 'string' || typeof a.state !== 'string') throw new Error('The hub returned an invalid action.');
      setFiled({ id: a.id, state: a.state, what: type === 'os.rollback' ? 'Go-back request' : 'Install request' });
      void history.reload();
    } catch (e) { setFailed(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  return <div className="dash-stack">
    <PageHeader title="OS updates" lede="The system version each machine runs, its A and B slots, and the update on offer. Requesting an install or going back files an approval; nothing changes from this page." />
    <Button onClick={() => { void status.reload(); void history.reload(); }}>Refresh updates</Button>
    {filed && <p role="status">{filed.what} {filed.id}: {filed.state}. It waits for the owner{filed.what === 'Go-back request' ? ', who approves it with a passkey' : filed.what === 'Settings change' ? ', who approves it with a passkey' : ''}. <Link to={href.approval(filed.id)}>Open request in Approvals</Link></p>}
    {failed && <p className="om-note om-tone-bad" role="status">Could not file the request: {failed}</p>}
    <Load res={status} what="Loading OS update status">{(s) => <>
      {s.install.available !== true && <p className="om-note om-tone-warn" role="note">Installing from the hub is not available yet. {text(s.install.message, '')}</p>}
      {s.nodes.length === 0 ? <p>No machine has reported yet.</p> : s.nodes.map((n) => {
        const rauc = record(n.rauc ?? {}, 'update status');
        const slots = Array.isArray(rauc.slots) ? list(rauc.slots, 'update status') : [];
        const node = text(n.node_id);
        const rb = record(n.rollback ?? {}, 'update status');
        const back = rb.available === true && typeof rb.version === 'string' && rb.version ? rb.version : undefined;
        const offer = typeof n.available_version === 'string' && n.available_version ? n.available_version : undefined;
        return <Card key={node} as="article" title={text(n.hostname, node)}>
          {n.reported !== true ? <p>This machine runs no update service.</p> : <dl className="om-facts">
            <div><dt>Running version</dt><dd>{text(n.current_version)}</dd></div>
            <div><dt>Channel</dt><dd>{text(n.channel)}</dd></div>
            <div><dt>Update state</dt><dd>{text(n.state)}</dd></div>
            <div><dt>Update on offer</dt><dd>{offer ?? 'None'}</dd></div>
            <div><dt>Booted slot</dt><dd>{text(rauc.booted_slot)}</dd></div>
            <div><dt>Last check</dt><dd>{text(n.last_check)}</dd></div>
            <div><dt>Last result</dt><dd>{text(n.last_result)}</dd></div>
            <div><dt>Previous version</dt><dd>{back ? `${back} (slot ${text(rb.slot)})` : `None. ${text(rb.message, 'It has not reported one.')}`}</dd></div>
          </dl>}
          {n.reported === true && <OsSettings client={client} node={n} available={s.settings.available === true} message={text(s.settings.message, '')}
            owner={canDecide !== 'no'} onFiled={(id, state) => { setFiled({ id, state, what: 'Settings change' }); void history.reload(); }} />}
          {slots.length > 0 && <ul aria-label={`Slots of ${node}`}>{slots.map((sl, i) => <li key={i}>Slot {text(sl.bootname, text(sl.name))} · {text(sl.state)} · {text(sl.boot_status)} · version {text(sl.bundle_version)}</li>)}</ul>}
          {offer && <Button disabled={busy} onClick={() => void request('os.update.install', node, offer)}>Request install of {offer}</Button>}
          {back && s.rollback.available !== true && <p className="om-note om-tone-warn" role="note">Going back from the hub is not available yet. {text(s.rollback.message, '')}</p>}
          {back && <>
            <p>Going back restarts this machine into {back}, the version it ran before. Your data stays. The owner confirms it with a passkey; nothing changes until then, and the health gate commits the old version after it boots.</p>
            <Button disabled={busy || s.rollback.available !== true} onClick={() => void request('os.rollback', node, back)}>Go back to {back}</Button>
          </>}
        </Card>;
      })}
    </>}</Load>
    <Load res={history} what="Loading update history">{(h) => <Card title="History">
      {h.events.length === 0 ? <p>No update has been committed or rolled back yet.</p> : <ul aria-label="Commits and rollbacks">{h.events.map((e, i) =>
        <li key={i}>{text(e.observed_at)} · {text(e.node_id)} · {e.state === 'rolled_back' ? 'Rolled back' : 'Committed'} · version {text(e.version)}{typeof e.last_result === 'string' && e.last_result ? ` · ${e.last_result}` : ''}</li>)}</ul>}
      {h.requests.length > 0 && <ul aria-label="Install requests">{h.requests.map((r, i) =>
        <li key={i}>{r.type === 'os.update.settings' ? `Update settings ${text(r.policy)}, window ${text(r.window)}` : `${r.type === 'os.rollback' ? 'Go back to' : 'Install'} ${text(r.version)}`} on {text(r.node_id)} · {text(r.state)}{typeof r.message === 'string' && r.message ? ` · ${r.message}` : ''}</li>)}</ul>}
    </Card>}</Load>
    <UpdatePolicy />
    <Fleet />
  </div>;
}
