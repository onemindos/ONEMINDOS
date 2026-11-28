// SPDX-License-Identifier: Apache-2.0
// Desktop apps from Flathub (issue #1097, D-026, D-027): search Flathub, ask to install, update or remove an app,
// open an installed one in a browser tab. Reads GET /v1/desktop-apps and /search; install, update, remove and
// launch file desktop.app.* requests for owner approval. Every app runs in
// its own sandbox with one folder of its own. While the box cannot run Flatpak the screen says so.
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
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
function text(v: unknown, missing = '') { return typeof v === 'string' && v ? v : missing; }
function apiError(e: unknown) {
  return e instanceof OneMindError ? new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason) : e;
}
async function call(client: OneMind, method: 'GET' | 'POST', path: string, body?: unknown) {
  try { return await client.call<unknown>({ method, path, body }); } catch (e) { throw apiError(e); }
}

export function DesktopApps() {
  const { token, person, mock } = useSignedIn();
  return mock ? <><PageHeader title="Desktop apps" /><p role="status">Connect to a real hub to manage desktop apps. Demo mode has no Flathub.</p></> : <LiveDesktopApps key={person} token={token} />;
}

function LiveDesktopApps({ token }: { token: string }) {
  const { canDecide } = useSignedIn();
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const status = usePoll(async () => {
    const s = record(await call(client, 'GET', '/v1/desktop-apps'), 'desktop apps status');
    return { service: record(s.service, 'desktop apps status'), installed: list(s.installed, 'desktop apps status'), stream: record(s.stream, 'desktop apps status') };
  }, 30_000);
  const [q, setQ] = useState('');
  const [results, setResults] = useState<Rec[]>();
  const [filed, setFiled] = useState<{ id: string; what: string }>();
  const [failed, setFailed] = useState<string>();
  const [busy, setBusy] = useState(false);

  const run = async (job: () => Promise<void>, what: string) => {
    setBusy(true); setFailed(undefined); setFiled(undefined);
    try { await job(); } catch (e) { setFailed(`${what}: ${e instanceof Error ? e.message : String(e)}`); } finally { setBusy(false); }
  };
  const search = () => run(async () => {
    const r = record(await call(client, 'GET', `/v1/desktop-apps/search?q=${encodeURIComponent(q.trim())}`), 'search result');
    setResults(list(r.results, 'search result'));
  }, 'Search failed');
  const ask = (verb: 'install' | 'update' | 'remove', id: string) => run(async () => {
    const a = record(await call(client, 'POST', '/v1/actions', {
      type: `desktop.app.${verb}`, params: { app_id: id }, idempotency_key: uuidv4(), expires_at: new Date(Date.now() + 24 * 3600_000).toISOString(),
    }), 'action');
    if (typeof a.id !== 'string') throw new Error('The hub returned an invalid action.');
    setFiled({ id: a.id, what: `${verb} ${id}` });
  }, `Could not ask to ${verb}`);
  const launch = (id: string) => run(async () => {
    const action = await client.call<components['schemas']['Action']>({
      method: 'POST', path: `/v1/desktop-apps/${encodeURIComponent(id)}/launch`,
      headers: { 'Idempotency-Key': uuidv4() }, retry: true,
    });
    setFiled({ id: action.id, what: `launch ${id}` });
  }, 'Could not ask to launch the app');

  return <div className="dash-stack">
    <PageHeader title="Desktop apps" lede="Install apps from Flathub and open them in your browser. Each app has a sandbox with its own folder. Installs, updates, removals and launches require owner approval." />
    <Button onClick={() => void status.reload()}>Refresh desktop apps</Button>
    {filed && <p role="status">Request {filed.id} to {filed.what} is waiting for an owner. <Link to={href.approval(filed.id)}>Open request in Approvals</Link></p>}
    {status.data?.stream.installed === true && <Link to="/apps/desktop-apps">Open the desktop session</Link>}
    {failed && <p className="om-note om-tone-bad" role="status">{failed}</p>}
    <Load res={status} what="Loading desktop apps">{(s) => {
      const available = s.service.available === true;
      const owner = canDecide === 'yes';
      return <>
        {!available && <p className="om-note om-tone-warn" role="note">Desktop apps are not available yet: {text(s.service.message, 'the box reports no Flatpak service.')}</p>}
        {available && <Card title="Find an app">
          <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 2) void search(); }}>
            <label htmlFor="flathub-q">Search Flathub</label>{' '}
            <input id="flathub-q" type="search" value={q} minLength={2} maxLength={64} onChange={(e) => setQ(e.target.value)} />{' '}
            <Button type="submit" disabled={busy || q.trim().length < 2}>Search</Button>
          </form>
          {results && (results.length === 0 ? <p>No app matches that search.</p> : <ul aria-label="Search results">{results.map((a) => {
            const id = text(a.app_id);
            return <li key={id}>
              {text(a.name, id)} · {id} · {text(a.version, 'no version')} · {text(a.summary, 'no description')}
              {a.installed === true ? ' · installed' : owner ? <> <Button disabled={busy} onClick={() => void ask('install', id)}>Ask to install {text(a.name, id)}</Button></> : null}
            </li>;
          })}</ul>)}
        </Card>}
        {available && (s.installed.length === 0 ? <p>No desktop apps are installed.</p> : <Card title="Installed">
          <ul aria-label="Installed desktop apps">{s.installed.map((a) => {
            const id = text(a.app_id);
            return <li key={id}>
              {text(a.name, id)} · {id} · {text(a.version, 'no version')} · its folder: <code>{text(a.folder, 'none')}</code>{a.update_available === true ? ' · update waiting' : ''}
              {owner && <>
                {' '}<Button disabled={busy} onClick={() => void launch(id)}>Ask to launch {text(a.name, id)}</Button>
                {a.update_available === true && <> <Button disabled={busy} onClick={() => void ask('update', id)}>Ask to update {text(a.name, id)}</Button></>}
                {' '}<Button variant="ghost" disabled={busy} onClick={() => void ask('remove', id)}>Ask to remove {text(a.name, id)}</Button>
              </>}
            </li>;
          })}</ul>
        </Card>)}
        {available && <p role="note">Sandbox for every app: {Array.isArray(s.service.sandbox) ? s.service.sandbox.map((x) => text(x)).join('; ') : 'one folder of its own'}. Removing an app keeps its folder.</p>}
      </>;
    }}</Load>
  </div>;
}
