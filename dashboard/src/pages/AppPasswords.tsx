// SPDX-License-Identifier: Apache-2.0
// Settings > Account and security > App passwords (files-webdav, #722), from /v1/files/app-passwords.
// Finder and Linux file managers open your files over WebDAV with a user name and a password; a gateway
// token or passkey cannot go there, so each device gets an app password of its own, with scopes. A new
// one is shown once; revoking one stops it on the next request. Only the owner and adults hold them.
import { useMemo, useState } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Card, Table } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { Load } from './parts';

type Row = { id: string; person_id: string; label: string; scopes: string[]; created_at: string; last_used_at: string | null };
type Made = { username: string; password: string; label: string };
const ACCESS = [['', 'No access'], ['r', 'Read only'], ['rw', 'Read and write']] as const;
const HOLDERS = new Set(['owner', 'adult']);

function apiError(e: unknown) {
  return e instanceof OneMindError ? new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason) : e;
}
async function call(client: OneMind, method: 'GET' | 'POST', path: string, body?: unknown) {
  try { return await client.call<unknown>({ method, path, body }); } catch (e) { throw apiError(e); }
}
function rows(v: unknown): Row[] {
  const list = v && typeof v === 'object' ? (v as { app_passwords?: unknown }).app_passwords : undefined;
  if (!Array.isArray(list)) throw new Error('The hub returned an invalid list of app passwords.');
  return list.filter((r): r is Row => !!r && typeof r === 'object' && typeof (r as Row).id === 'string' && Array.isArray((r as Row).scopes));
}
function scopeText(scopes: string[]) {
  return scopes.map((s) => { const [space, access] = s.split(':'); return `${space === 'home' ? 'My files' : 'Shared'} ${access === 'rw' ? 'read and write' : 'read only'}`; }).join(', ');
}

export function AppPasswords() {
  const { token, mock } = useSignedIn();
  const { role } = useShell();
  if (mock) return <Card title="App passwords"><p role="status">Connect to a real hub to manage app passwords. Demo mode has none.</p></Card>;
  if (role === undefined || role === null || !HOLDERS.has(role)) return null; // fail closed while the role loads
  return <LiveAppPasswords token={token} />;
}

function LiveAppPasswords({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const list = usePoll(async () => rows(await call(client, 'GET', '/v1/files/app-passwords')), 0);
  const [label, setLabel] = useState('');
  const [home, setHome] = useState('rw');
  const [shared, setShared] = useState('r');
  const [made, setMade] = useState<Made>();
  const [failed, setFailed] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState<string>();
  const host = window.location.hostname;

  const run = async (job: () => Promise<void>, what: string) => {
    setBusy(true); setFailed(undefined);
    try { await job(); void list.reload(); } catch (e) {
      const stepUp = e instanceof ApiError && e.reason === 'step_up_required';
      setFailed(`${what}: ${stepUp ? 'this needs a fresh passkey sign-in; sign out, sign in with your passkey and try again' : e instanceof Error ? e.message : String(e)}`);
    } finally { setBusy(false); }
  };
  const scopes = [home && `home:${home}`, shared && `shared:${shared}`].filter(Boolean);
  const create = () => run(async () => {
    setMade(undefined);
    const r = await call(client, 'POST', '/v1/files/app-passwords', { label: label.trim(), scopes }) as Partial<Made>;
    if (typeof r.username !== 'string' || typeof r.password !== 'string') throw new Error('The hub returned an invalid app password.');
    setMade({ username: r.username, password: r.password, label: label.trim() });
    setLabel('');
  }, 'Could not make the app password');
  const revoke = (id: string) => run(async () => {
    await call(client, 'POST', `/v1/files/app-passwords/${encodeURIComponent(id)}/revoke`);
    setConfirming(undefined);
  }, 'Could not revoke the app password');

  return <Card title="App passwords">
    <p>Open your files from a Mac (Finder, Go, Connect to Server: <code>https://{host}/dav/</code>) or Linux (Files, Other Locations: <code>davs://{host}/dav/</code>) on your home network or mesh. Make one password per device, so you can revoke one without the others. On Windows, use File sharing (SMB) instead.</p>
    {failed && <p className="om-note om-tone-bad" role="status">{failed}</p>}
    {made && <p role="status">App password for {made.label}: user name <code>{made.username}</code>, password <code>{made.password}</code>. It is shown once and cannot be looked up again.</p>}
    <form onSubmit={(e) => { e.preventDefault(); void create(); }}>
      <p><label htmlFor="apw-label">Device or app</label>{' '}
        <input id="apw-label" value={label} maxLength={64} placeholder="MacBook Finder" onChange={(e) => setLabel(e.target.value)} /></p>
      <p><label htmlFor="apw-home">My files</label>{' '}
        <select id="apw-home" value={home} onChange={(e) => setHome(e.target.value)}>{ACCESS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>{' '}
        <label htmlFor="apw-shared">Shared</label>{' '}
        <select id="apw-shared" value={shared} onChange={(e) => setShared(e.target.value)}>{ACCESS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></p>
      <Button type="submit" disabled={busy || !label.trim() || scopes.length === 0}>Make an app password</Button>
    </form>
    <Load res={list} what="Loading app passwords">{(items) => items.length === 0 ? <p className="om-hint">No app passwords yet.</p> : <Table
      caption="App passwords" hideCaption rows={items} rowKey={(r) => r.id}
      columns={[
        { key: 'label', header: 'Device', render: (r) => r.label },
        { key: 'who', header: 'User name', render: (r) => r.person_id, secondary: true },
        { key: 'scopes', header: 'Reaches', render: (r) => scopeText(r.scopes), secondary: true },
        { key: 'used', header: 'Last used', render: (r) => r.last_used_at ? new Date(r.last_used_at).toLocaleString() : 'Never', secondary: true },
        { key: 'x', header: 'Actions', render: (r) => confirming === r.id
          ? <><Button size="sm" disabled={busy} onClick={() => void revoke(r.id)}>Confirm revoke {r.label}</Button> <Button size="sm" variant="ghost" onClick={() => setConfirming(undefined)}>Keep</Button></>
          : <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirming(r.id)}>Revoke {r.label}</Button> },
      ]} />}</Load>
  </Card>;
}
