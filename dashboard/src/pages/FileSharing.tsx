// SPDX-License-Identifier: Apache-2.0
// File sharing (FILES-SHARE-01, #235): who has an SMB share of their files and a Time Machine
// target, from GET /v1/shares/smb. Turning a share on only files a files.share.create request;
// nothing is shared until an owner approves it. While the box has no file-sharing service the
// screen says so and offers nothing to press.
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load } from './parts';

const GIB = 1024 ** 3;
const SIZES = [100, 250, 500, 1000];

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

export function FileSharing() {
  const { token, person, mock } = useSignedIn();
  return mock ? <><PageHeader title="File sharing" /><p role="status">Connect to a real hub to manage file sharing. Demo mode has no share data.</p></> : <LiveSharing key={person} token={token} />;
}

function LiveSharing({ token }: { token: string }) {
  const { canDecide } = useSignedIn();
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const status = usePoll(async () => {
    const s = record(await call(client, 'GET', '/v1/shares/smb'), 'file sharing status');
    return { service: record(s.service, 'file sharing status'), people: list(s.people, 'file sharing status'), shares: list(s.shares, 'file sharing status') };
  }, 30_000);
  const [filed, setFiled] = useState<{ id: string; state: string }>();
  const [failed, setFailed] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [size, setSize] = useState(String(SIZES[2]));
  const [confirming, setConfirming] = useState<string>();

  const run = async (job: () => Promise<void>, what: string) => {
    setBusy(true); setFailed(undefined); setFiled(undefined);
    try { await job(); void status.reload(); } catch (e) { setFailed(`${what}: ${e instanceof Error ? e.message : String(e)}`); } finally { setBusy(false); }
  };
  const request = (kind: 'home' | 'timemachine', personId: string) => run(async () => {
    const params = kind === 'home' ? { kind, person_id: personId } : { kind, person_id: personId, quota_bytes: Number(size) * GIB };
    const a = record(await call(client, 'POST', '/v1/actions', {
      type: 'files.share.create', params, idempotency_key: uuidv4(), expires_at: new Date(Date.now() + 24 * 3600_000).toISOString(),
    }), 'action');
    if (typeof a.id !== 'string' || typeof a.state !== 'string') throw new Error('The hub returned an invalid action.');
    setFiled({ id: a.id, state: a.state });
  }, 'Could not file the request');
  const stop = (id: string) => run(async () => { await call(client, 'POST', `/v1/shares/smb/${encodeURIComponent(id)}/stop`); setConfirming(undefined); }, 'Could not stop sharing');

  return <div className="dash-stack">
    <PageHeader title="File sharing" lede="Open your files from a Mac, a Windows PC or a Linux machine on your home network, over SMB, and back up a Mac with Time Machine. Off by default, reachable from your network and your mesh only, one share per person that shows only that person's files." />
    <Button onClick={() => void status.reload()}>Refresh file sharing</Button>
    {filed && <p role="status">Request {filed.id}: {filed.state}. Nothing is shared until an owner approves it. <Link to={href.approval(filed.id)}>Open request in Approvals</Link></p>}
    {failed && <p className="om-note om-tone-bad" role="status">{failed}</p>}
    <Load res={status} what="Loading file sharing">{(s) => {
      const available = s.service.available === true;
      const owner = canDecide === 'yes';
      return <>
        {!available && <p className="om-note om-tone-warn" role="note">File sharing is not available yet: {text(s.service.message, 'the box reports no file-sharing service.')}</p>}
        {available && !owner && <p role="note">An owner turns sharing on; you can see your own shares here.</p>}
        {s.shares.length === 0 ? <p>Nothing is shared.</p> : <Card title="Shares">
          <ul aria-label="Shares">{s.shares.map((sh) => {
            const id = text(sh.id); const name = text(sh.name);
            return <li key={id}>
              {name} · {sh.kind === 'timemachine' ? `Time Machine for ${text(sh.person_id)}${typeof sh.quota_bytes === 'number' ? `, up to ${Math.round(sh.quota_bytes / GIB)} GB` : ''}` : `${text(sh.person_id)}'s files`} · {text(sh.state)}
              {owner && (confirming === id
                ? <> <Button disabled={busy} onClick={() => void stop(id)}>Confirm stop sharing {name}</Button> <Button variant="ghost" onClick={() => setConfirming(undefined)}>Keep sharing</Button></>
                : <> <Button disabled={busy} onClick={() => setConfirming(id)}>Stop sharing {name}</Button></>)}
            </li>;
          })}</ul>
        </Card>}
        {available && owner && s.people.filter((p) => p.home === true).map((p) => {
          const pid = text(p.person_id);
          const has = (k: string) => s.shares.some((sh) => sh.person_id === pid && sh.kind === k);
          if (has('home') && has('timemachine')) return null;
          return <Card key={pid} as="article" title={pid}>
            {!has('home') && <Button disabled={busy} onClick={() => void request('home', pid)}>Ask to share {pid}'s files</Button>}
            {!has('timemachine') && <p>
              <label htmlFor={`tm-${pid}`}>Time Machine size for {pid}</label>{' '}
              <select id={`tm-${pid}`} value={size} onChange={(e) => setSize(e.target.value)}>{SIZES.map((g) => <option key={g} value={g}>{g >= 1000 ? `${g / 1000} TB` : `${g} GB`}</option>)}</select>{' '}
              <Button disabled={busy} onClick={() => void request('timemachine', pid)}>Ask for a Time Machine share for {pid}</Button>
            </p>}
          </Card>;
        })}
      </>;
    }}</Load>
  </div>;
}
