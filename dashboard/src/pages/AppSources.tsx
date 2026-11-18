// SPDX-License-Identifier: Apache-2.0
// Market tabs for contract §12.22 (#57): community sources pinned at a commit, and Compose import.
// Adding a source is a `source.add` request: nothing is fetched until the owner approves it in
// Approvals. Compose import only converts (POST /v1/deploy/compose); it writes nothing on the box.
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { Button, Dialog, PageHeader, useToast } from '@onemind/ui';
import { ApiError, type ComposeResult } from '../api/types';
import type { SourceAddParams } from '../api/client';
import { errorText, useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { StoreTabs } from './Market';

const REQUEST_TTL_MS = 24 * 3600 * 1000;

export function Sources() {
  const { api } = useSignedIn();
  const hub = useHub();
  const toast = useToast();
  const navigate = useNavigate();
  const list = usePoll(async () => {
    if (!api.sources) throw new Error('Sources cannot be read by this gateway client.');
    return api.sources();
  }, 30_000);
  const [form, setForm] = useState<SourceAddParams>({ name: '', url: '', commit: '' });
  const [review, setReview] = useState<SourceAddParams>();
  const [sending, setSending] = useState(false);
  // One idempotency key per exact request, kept only while its outcome is unknown (retry = same key).
  const keys = useRef(new Map<string, { idempotency_key: string; expires_at: string }>());
  const send = async (params: SourceAddParams) => {
    setReview(undefined);
    if (!api.requestSourceAdd) return;
    const slot = JSON.stringify(params);
    const key = keys.current.get(slot) ?? { idempotency_key: uuidv4(), expires_at: new Date(Date.now() + (api.hubOffsetMs() ?? 0) + REQUEST_TTL_MS).toISOString() };
    keys.current.set(slot, key);
    setSending(true);
    try {
      const action = await api.requestSourceAdd(params, key);
      keys.current.delete(slot);
      toast.show({ tone: 'info', title: 'Request sent', body: 'Nothing is fetched until the owner approves it in Approvals.' });
      navigate(href.approval(action.id));
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) keys.current.delete(slot);
      toast.show({ tone: 'bad', title: 'Could not request the source', body: errorText(e).message });
    } finally {
      setSending(false);
    }
  };
  const set = (k: keyof SourceAddParams) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: k === 'commit' ? e.target.value.trim().toLowerCase() : e.target.value });
  return <>
    <PageHeader title="Community sources" lede="Extra app catalogs from a git repository, pinned at one commit. Their apps are scanned on this box before any install." />
    <StoreTabs current="sources" />
    <section aria-label="Pinned sources">
      <h2>Pinned sources</h2>
      {list.error ? <p role="alert">{list.error.message}</p> : !list.data ? <p role="status">Loading sources…</p> : list.data.length === 0 ? <p>No community source is pinned. Only the official catalog is offered.</p> : <ul>
        {list.data.map((s) => <li key={s.id}>
          <p><strong>{s.name}</strong> — {s.url} at <code>{s.commit.slice(0, 12)}</code>{s.state !== 'ready' ? ` (${s.state.replace(/_/g, ' ')})` : ''}</p>
          <ul aria-label={`Apps from ${s.name}`}>{s.apps.map((a) => <li key={a.id}><a href={href.app(a.id)}>{a.id}</a> {a.version} — scan: {a.scan ? a.scan.result : 'not scanned yet'}</li>)}</ul>
          {s.errors.length > 0 && <p role="alert">Skipped: {s.errors.join('; ')}</p>}
        </li>)}
      </ul>}
    </section>
    <section aria-label="Add a source">
      <h2>Add a pinned source</h2>
      <form onSubmit={(e) => { e.preventDefault(); setReview(form); }}>
        <p><label>Name<input required pattern="[a-z0-9]([a-z0-9\-]{0,18}[a-z0-9])?" maxLength={20} value={form.name} onChange={set('name')} /></label><small>Lowercase letters, digits and dashes.</small></p>
        <p><label>Git URL<input required type="url" pattern="https://.+" maxLength={500} value={form.url} onChange={set('url')} /></label><small>https only, no user name or query.</small></p>
        <p><label>Commit<input required pattern="[0-9a-f]{40}" minLength={40} maxLength={40} value={form.commit} onChange={set('commit')} /></label><small>The full 40-character commit id. A branch name is not accepted: a pin never moves by itself.</small></p>
        <Button type="submit" disabled={sending || hub.canRequest === 'no'}>Review source</Button>
      </form>
      <p className="om-hint">Only an owner may add a source, and an owner approves it in Approvals before anything is fetched.</p>
    </section>
    {review && <Dialog open title="Review source request" onClose={() => setReview(undefined)} actions={<><Button onClick={() => setReview(undefined)}>Cancel</Button><Button variant="primary" onClick={() => void send(review)}>Send request</Button></>}>
      <p>Add source <strong>{review.name}</strong> from {review.url} pinned at commit <code>{review.commit}</code>.</p>
      <p className="om-hint">Nothing runs now. An owner must approve this request in Approvals.</p>
    </Dialog>}
  </>;
}

export function ComposeImport() {
  const { api } = useSignedIn();
  const [appId, setAppId] = useState('');
  const [name, setName] = useState('');
  const [text, setText] = useState('');
  const [result, setResult] = useState<ComposeResult>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const convert = async () => {
    if (!api.convertCompose) return;
    setBusy(true);
    setError(undefined);
    try {
      setResult(await api.convertCompose({ app_id: appId, compose: text, ...(name ? { name } : {}) }));
    } catch (e) {
      setResult(undefined);
      setError(errorText(e).message);
    } finally {
      setBusy(false);
    }
  };
  return <>
    <PageHeader title="Import a Compose file" lede="Convert a docker-compose.yml into a OneMind app folder. The conversion writes nothing and installs nothing." />
    <StoreTabs current="compose" />
    <form onSubmit={(e) => { e.preventDefault(); void convert(); }}>
      <p><label>App id<input required pattern="[a-z0-9]([a-z0-9\-]{0,57}[a-z0-9])?" maxLength={59} value={appId} onChange={(e) => setAppId(e.target.value)} /></label></p>
      <p><label>Display name (optional)<input maxLength={80} value={name} onChange={(e) => setName(e.target.value)} /></label></p>
      <p><label>Compose file<textarea required rows={12} value={text} onChange={(e) => setText(e.target.value)} /></label></p>
      <Button type="submit" disabled={busy}>Convert</Button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <section aria-label="Conversion result">
      <h2>{result.ok ? `Converted ${result.app_id}` : `${result.app_id} cannot be imported`}</h2>
      {result.refusals.length > 0 && <div role="alert"><p>Refused by the install sandbox rules:</p><ul>{result.refusals.map((r, i) => <li key={i}>{r.rule}{r.service ? ` (${r.service})` : ''} {r.field}: {r.message}</li>)}</ul></div>}
      {result.warnings.length > 0 && <><h3>Warnings</h3><ul>{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></>}
      {result.ok && <>
        <p>Nothing was installed. To offer this app, commit these files to a git repository and add it under Sources; its install then waits for owner approval like any other.</p>
        {Object.entries(result.files).map(([path, body]) => <details key={path}><summary>{path}</summary><pre>{body}</pre></details>)}
      </>}
    </section>}
  </>;
}
