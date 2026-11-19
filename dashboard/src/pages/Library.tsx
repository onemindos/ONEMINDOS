// SPDX-License-Identifier: Apache-2.0
// Offline library (NMD-02, #127): the Kiwix books this box keeps, curated packs, Wikipedia by size
// and language, updates and the auto-update check. Every change shows its download size first and
// is filed as a request (an app.configure of Kiwix) that waits for the owner's approval; this page
// never approves. Types come from the generated client (@onemind/sdk), routes from core/routers/content.py.
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, uuid4, type components } from '@onemind/sdk';
import { Button, Card, Dialog, PageHeader } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load } from './parts';

type S = components['schemas'];
type BookRef = S['BookRef'];
type Plan = S['ContentPlan'];
type Proposal = { title: string; add: BookRef[]; remove: BookRef[]; plan: Plan };

export function bytes(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)} MB`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)} kB`;
  return `${n} bytes`;
}
function err(e: unknown): ApiError {
  if (e instanceof OneMindError) return new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
  return e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e));
}
async function call<T>(sdk: OneMind, method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown): Promise<T> {
  try { return await sdk.call<T>({ method, path, body }); } catch (e) { throw err(e); }
}

export function Library() {
  const { token, person, mock } = useSignedIn();
  if (mock) return <><PageHeader title="Offline library" /><p role="status">Connect to a real hub to manage offline content. Demo mode has no Kiwix catalogue.</p></>;
  return <LiveLibrary key={person} token={token} />;
}

function LiveLibrary({ token }: { token: string }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const view = usePoll(() => call<S['ContentView']>(sdk, 'GET', '/v1/content'), 30_000);
  const [proposal, setProposal] = useState<Proposal>();
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState<string>();
  const [lang, setLang] = useState('en');
  const [wiki, setWiki] = useState<S['WikipediaChoices']>();

  const run = async (job: () => Promise<void>) => {
    setBusy(true); setNote('');
    try { await job(); } catch (e) { setNote(err(e).message); } finally { setBusy(false); }
  };
  // Every change starts with a plan: the books to download with their size, before anything is filed.
  const propose = (title: string, add: BookRef[], remove: BookRef[]) => run(async () => {
    const plan = await call<Plan>(sdk, 'POST', '/v1/content/plan', { add, remove });
    if (!plan.changed) { setNote('The library already has exactly these books.'); return; }
    setProposal({ title, add, remove, plan });
  });
  const checkUpdates = () => run(async () => {
    const plan = await call<Plan>(sdk, 'GET', '/v1/content/updates');
    if (!plan.changed) { setNote('Every book is the newest release.'); return; }
    setProposal({ title: 'Update books', add: plan.downloads.map((b) => ({ name: b.name, flavour: b.flavour })), remove: [], plan });
  });
  const send = (p: Proposal) => run(async () => {
    const out = await call<S['ContentChangeResult']>(sdk, 'POST', '/v1/content/changes',
      { add: p.add, remove: p.remove, download_bytes: p.plan.download_bytes, idempotency_key: uuid4() });
    setReceipt(out.action.id); setProposal(undefined); void view.reload();
  });
  const showWikipedia = () => run(async () => {
    setWiki(await call<S['WikipediaChoices']>(sdk, 'GET', `/v1/content/wikipedia?lang=${encodeURIComponent(lang.trim().toLowerCase())}`));
  });
  const setAuto = (enabled: boolean, windowId: string) => run(async () => {
    await call<S['AutoUpdate']>(sdk, 'PUT', '/v1/content/auto-update', { enabled, window_id: windowId });
    void view.reload();
  });

  return <div className="dash-stack">
    <PageHeader title="Offline library" lede="Wikipedia and reference books served by the Kiwix app, readable without internet. Sizes come from the live Kiwix catalogue; every change waits for the owner's approval." />
    {note && <p role="status">{note}</p>}
    {receipt && <p role="status">Request {receipt} filed. Nothing downloads until it is approved. <Link to={href.approval(receipt)}>Open request in Approvals</Link></p>}
    <Dialog role="alertdialog" open={proposal !== undefined} onClose={() => { if (!busy) setProposal(undefined); }}
      title={proposal?.title ?? ''} description="This files a request. Nothing downloads or stops being served until the owner approves it."
      actions={proposal && <Button disabled={busy} onClick={() => void send(proposal)}>{busy ? 'Sending request…' : `Request (${bytes(proposal.plan.download_bytes)} to download)`}</Button>}>
      {proposal && <>
        <p><strong>Download: {bytes(proposal.plan.download_bytes)}</strong></p>
        {proposal.plan.downloads.length > 0 && <ul>{proposal.plan.downloads.map((b) => <li key={b.path}>{b.title} ({b.flavour || 'standard'}) · {bytes(b.size_bytes)}</li>)}</ul>}
        {proposal.plan.removed.length > 0 && <><p>Stops being served (the file stays on disk until you delete it):</p><ul>{proposal.plan.removed.map((p) => <li key={p}>{p}</li>)}</ul></>}
      </>}
    </Dialog>
    <Load res={view} what="Loading the offline library">{(v) => <>
      {!v.app.in_catalog ? <p role="status">The Kiwix app is not in this box's catalogue, so there is no offline library to manage.</p>
        : v.app.status !== 'installed' && <p role="status">Kiwix is {v.app.status.replace('_', ' ')}. Install it from the <Link to={href.app('kiwix')}>Market</Link> to serve these books.</p>}
      {v.pending_action_id && <p role="status">A library change waits for approval. <Link to={href.approval(v.pending_action_id)}>Open it in Approvals</Link></p>}
      <Card title="In the library">
        {v.library.length === 0 ? <p>No books yet.</p> : <ul>{v.library.map((b) => <li key={b.path}>
          <strong>{b.name}</strong>{b.flavour ? ` · ${b.flavour}` : ''}{b.date ? ` · ${b.date}` : ''}{' '}
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void propose(`Remove ${b.name}`, [], [{ name: b.name, flavour: b.flavour }])}>Remove</Button>
        </li>)}</ul>}
        <Button variant="secondary" disabled={busy || !v.app.in_catalog} onClick={() => void checkUpdates()}>Check for updates</Button>
      </Card>
      <Card title="Packs">
        {v.packs.map((p) => {
          const missing = p.books.filter((b) => !b.in_library).map((b) => ({ name: b.name, flavour: b.flavour }));
          return <article key={p.id} aria-label={p.title}>
            <h3>{p.title}</h3>
            <p>{p.description}</p>
            <ul>{p.books.map((b) => <li key={`${b.name}_${b.flavour}`}>{b.name}{b.flavour ? ` · ${b.flavour}` : ''}{b.in_library ? ' · in the library' : ''}</li>)}</ul>
            <Button size="sm" disabled={busy || missing.length === 0 || !v.app.in_catalog} onClick={() => void propose(`Add the ${p.title} pack`, missing, [])}>
              {missing.length === 0 ? 'All in the library' : 'Show download size'}
            </Button>
          </article>;
        })}
      </Card>
      <Card title="Wikipedia">
        <label>Language code <input value={lang} maxLength={21} onChange={(e) => setLang(e.target.value)} /></label>{' '}
        <Button size="sm" disabled={busy || !v.app.in_catalog} onClick={() => void showWikipedia()}>Show sizes</Button>
        {wiki && (wiki.books.length === 0 ? <p>The catalogue has no Wikipedia in “{wiki.lang}”.</p>
          : <ul>{wiki.books.map((b) => <li key={b.path}>{b.flavour} · {bytes(b.size_bytes)}{' '}
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void propose(`Add Wikipedia (${wiki.lang}, ${b.flavour})`, [{ name: b.name, flavour: b.flavour }], [])}>Choose</Button>
          </li>)}</ul>)}
      </Card>
      <Card title="Automatic updates">
        <p>{v.auto_update.enabled
          ? `On. Inside the maintenance window ${v.auto_update.window_id} the box checks for newer releases and requests them; you still approve each download.`
          : 'Off. Updates are only checked when you ask.'}</p>
        {v.auto_update.last_result && <p>Last check{v.auto_update.last_checked_at ? ` (${v.auto_update.last_checked_at})` : ''}: {v.auto_update.last_result}</p>}
        <Button size="sm" disabled={busy} onClick={() => void setAuto(!v.auto_update.enabled, v.auto_update.window_id)}>
          {v.auto_update.enabled ? 'Turn automatic updates off' : 'Turn automatic updates on'}
        </Button>
      </Card>
    </>}</Load>
  </div>;
}
