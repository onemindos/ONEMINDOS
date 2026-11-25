// SPDX-License-Identifier: Apache-2.0
// Settings > Account and security > SSH keys (P-06), from GET /v1/ssh. SSH is the owner's everyday shell
// on the box and the way in when this screen is down: public key only, as admin, from the home network and
// the mesh (and the internet on a cloud box), slowed to a few new connections a minute per address. Every change here only files a
// request; nothing changes until an owner approves it in Approvals, and letting a key in or switching SSH
// on needs a passkey there once passkeys are active. Only an owner sees this card.
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, Table } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load } from './parts';

// The gateway's own response types (generated from core/onemind_core/routers/ssh.py through the OpenAPI spec).
type Key = components['schemas']['SshKey'];
type View = components['schemas']['SshView'];

const STATE: Record<string, string> = {
  on: 'On, and listening',
  off: 'Off, also after a restart',
  waiting_for_key: 'On, waiting for the first key (nothing listens until a key is added)',
  starting: 'On, starting',
};

function apiError(e: unknown) {
  return e instanceof OneMindError ? new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason) : e;
}
async function call(client: OneMind, method: 'GET' | 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown, headers?: Record<string, string>) {
  try { return await client.call<unknown>({ method, path, body, headers }); } catch (e) { throw apiError(e); }
}
function view(v: unknown): View {
  const o = v && typeof v === 'object' ? (v as Partial<View>) : undefined;
  if (!o || !o.service || typeof o.service.state !== 'string' || !Array.isArray(o.keys)) throw new Error('The hub returned an invalid SSH status.');
  return { service: o.service, keys: o.keys.filter((k): k is Key => !!k && typeof k.id === 'string' && typeof k.fingerprint === 'string') };
}

export function SshKeys() {
  const { token, mock, principal } = useSignedIn();
  if (principal?.role !== 'owner') return null;
  if (mock) return <Card title="SSH keys"><p role="status">Connect to a real hub to manage SSH keys. Demo mode shows no SSH keys.</p></Card>;
  return <LiveSshKeys token={token} />;
}

function LiveSshKeys({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const status = usePoll(async () => view(await call(client, 'GET', '/v1/ssh')), 0);
  const [key, setKey] = useState('');
  const [label, setLabel] = useState('');
  const [filed, setFiled] = useState<{ id: string; what: string }>();
  const [failed, setFailed] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState<string>();

  const file = async (job: () => Promise<unknown>, what: string) => {
    setBusy(true); setFailed(undefined); setFiled(undefined);
    try {
      const a = await job() as { id?: unknown };
      if (typeof a?.id !== 'string') throw new Error('The hub returned an invalid request.');
      setFiled({ id: a.id, what });
      setConfirming(undefined);
      void status.reload();
    } catch (e) { setFailed(`Could not ask to ${what}: ${e instanceof Error ? e.message : String(e)}`); } finally { setBusy(false); }
  };
  const add = () => file(async () => {
    const r = await call(client, 'POST', '/v1/ssh/keys', { public_key: key.trim(), ...(label.trim() ? { label: label.trim() } : {}), idempotency_key: uuidv4() });
    setKey(''); setLabel('');
    return r;
  }, 'add the key');
  // A DELETE has no body, so its idempotency key goes in the header: a retried click files one removal, not two.
  const remove = (k: Key) => file(() => call(client, 'DELETE', `/v1/ssh/keys/${encodeURIComponent(k.id)}`, undefined, { 'Idempotency-Key': uuidv4() }), 'remove the key');
  const toggle = (enabled: boolean) => file(() => call(client, 'PUT', '/v1/ssh', { enabled, idempotency_key: uuidv4() }), enabled ? 'switch SSH on' : 'switch SSH off');

  return <Card title="SSH keys">
    <p>SSH is a shell on this box for you, the owner: public key only (no password), as <code>admin</code>, from your home network or mesh, and slowed to a few new connections a minute per address. It is also the way in if this screen is down. Every change below is a request that an owner approves in Approvals, with a passkey to let a key in or switch SSH on.</p>
    {filed && <p role="status">Asked to {filed.what}. Nothing changes until an owner approves it. <Link to={href.approval(filed.id)}>Open request in Approvals</Link></p>}
    {failed && <p className="om-note om-tone-bad" role="status">{failed}</p>}
    <Load res={status} what="Loading SSH">{(s) => {
      const state = s.service.state;
      const off = state === 'off';
      const internet = Array.isArray(s.service.reach) && s.service.reach.includes('internet');
      return <>
        {internet && <p className="om-note om-tone-warn" role="note">This is a cloud box: SSH also answers from the internet, still with a key only and the same limit on new connections.</p>}
        {!s.service.available
          ? <p className="om-note om-tone-warn" role="note">SSH is not available on this box: {s.service.message ?? 'the host service gave no answer.'}</p>
          : <p role="status">SSH: {STATE[state] ?? state}. <Button size="sm" variant="ghost" disabled={busy} onClick={() => void toggle(off)}>{off ? 'Ask to switch SSH on' : 'Ask to switch SSH off'}</Button></p>}
        {s.service.available && <>
          {s.keys.length === 0 ? <p className="om-hint">No SSH keys yet. Add one to let a computer log in.</p> : <Table
            caption="SSH keys" hideCaption rows={s.keys} rowKey={(k) => k.id}
            columns={[
              { key: 'name', header: 'Name', render: (k) => k.comment || 'No name' },
              { key: 'type', header: 'Type', render: (k) => `${k.type}${k.bits ? ` ${k.bits}` : ''}`, secondary: true },
              { key: 'fp', header: 'Fingerprint', render: (k) => <code>{k.fingerprint}</code>, secondary: true },
              { key: 'x', header: 'Actions', render: (k) => confirming === k.id
                ? <><Button size="sm" disabled={busy} onClick={() => void remove(k)}>Confirm remove {k.comment || k.id}</Button> <Button size="sm" variant="ghost" onClick={() => setConfirming(undefined)}>Keep</Button></>
                : <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirming(k.id)}>Remove {k.comment || k.id}</Button> },
            ]} />}
          {s.keys.length < s.service.max_keys && <form onSubmit={(e) => { e.preventDefault(); void add(); }}>
            <p><label htmlFor="ssh-key">Public key (the one line of your .pub file)</label><br />
              <textarea id="ssh-key" rows={3} cols={60} value={key} spellCheck={false} placeholder="ssh-ed25519 AAAA... you@laptop" onChange={(e) => setKey(e.target.value)} /></p>
            <p><label htmlFor="ssh-label">Name (optional)</label>{' '}
              <input id="ssh-label" value={label} maxLength={60} placeholder="Work laptop" onChange={(e) => setLabel(e.target.value)} /></p>
            <Button type="submit" disabled={busy || !key.trim()}>Ask to add this key</Button>
          </form>}
        </>}
      </>;
    }}</Load>
  </Card>;
}
