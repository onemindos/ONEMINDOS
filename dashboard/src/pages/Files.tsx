// SPDX-License-Identifier: Apache-2.0
// The Files window (FILES-01, D-016): browse, upload over tus, download, preview, trash, and ask for
// folder access. Putting a file in the trash is the person's own click on their own files; anything
// that gives access away or destroys data for good (a grant, emptying the trash) is filed as an
// approval request bound to its exact plan, and decided in the Sharing tab by a person, never by this page.
import { useEffect, useMemo, useRef, useState } from 'react';
import { uuid4 } from '@onemind/sdk';
import { Button, Card, Dialog, PageHeader, StatusPill } from '@onemind/ui';
import { FilesApi, human, type Entry, type FileRequest, type FileRoot, type Preview, type TrashItem } from '../files/api';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { FilesQuotas } from './FilesQuotas';
import { FilesDropZone, FilesFooter, FilesLayout } from './files/FilesAtlas';
import { Load, TextField, useRun } from './parts';

type Tab = 'files' | 'trash' | 'sharing' | 'quotas';
const parent = (p: string) => p.replace(/\/[^/]+$/, '') || '/';
const when = (iso: string) => (Number.isNaN(Date.parse(iso)) ? iso : new Date(iso).toLocaleString());

export function Files() {
  const { token, person, mock, principal } = useSignedIn();
  if (mock) return <><PageHeader title="Files" /><p role="status">Connect to a real hub to browse files. Demo mode has no file storage.</p></>;
  return <LiveFiles key={person} token={token} person={person} owner={principal?.role === 'owner'} />;
}

function LiveFiles({ token, person, owner }: { token: string; person: string; owner: boolean }) {
  const api = useMemo(() => new FilesApi(token), [token]);
  const run = useRun();
  const roots = usePoll(() => api.roots(), 60_000);
  const [tab, setTab] = useState<Tab>('files');
  const [root, setRoot] = useState<FileRoot>();
  const current = root ?? roots.data?.[0];
  return <div className="dash-stack">
    <PageHeader title="Files" lede="Your files on your box. Sharing access with an app or agent, and emptying the trash for good, are requests a person approves." />
    <div role="group" aria-label="Files sections">
      {(owner ? ['files', 'trash', 'sharing', 'quotas'] as const : ['files', 'trash', 'sharing'] as const).map((t) => <Button key={t} variant={tab === t ? 'primary' : 'secondary'} aria-pressed={tab === t} onClick={() => setTab(t)}>{t === 'files' ? 'Files' : t === 'trash' ? 'Trash' : t === 'sharing' ? 'Sharing' : 'Storage limits'}</Button>)}
    </div>
    <Load res={roots} what="Loading your spaces">{(rs) => rs.length === 0 ? <p>No space is available to this account.</p> : <>
      {tab === 'files' && <FilesLayout roots={rs} current={current} onPick={setRoot}>
        {current && <Browser key={current.root} api={api} space={current} run={run} onChanged={() => void roots.reload()} />}
      </FilesLayout>}
      {tab === 'trash' && <TrashTab api={api} run={run} />}
      {tab === 'quotas' && owner && <FilesQuotas api={api} run={run} />}
      {tab === 'sharing' && <Sharing api={api} run={run} person={person} roots={rs} />}
    </>}</Load>
  </div>;
}

type Run = ReturnType<typeof useRun>;

function Browser({ api, space, run, onChanged }: { api: FilesApi; space: FileRoot; run: Run; onChanged: () => void }) {
  const [dir, setDir] = useState(space.path);
  const entries = usePoll(() => api.list(space.root, dir), 30_000);
  const [seen, setSeen] = useState<{ entry: Entry; preview?: Preview; image?: string; error?: string }>();
  const [folderOpen, setFolderOpen] = useState(false);
  const [name, setName] = useState('');
  const [doomed, setDoomed] = useState<Entry>();
  const [progress, setProgress] = useState<{ name: string; done: number; total: number }>();
  const [uploadError, setUploadError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const crumbs = dir.split('/').filter(Boolean);
  const imageUrl = useRef<string | undefined>(undefined);
  useEffect(() => { void entries.reload(); }, [dir]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (imageUrl.current) URL.revokeObjectURL(imageUrl.current); }, []);

  const open = (e: Entry) => { if (e.type === 'dir') { setDir(e.path); setSeen(undefined); } else void look(e); };
  const look = async (entry: Entry) => {
    setSeen({ entry });
    try {
      const preview = await api.preview(space.root, entry.path);
      let image: string | undefined;
      if (preview.kind === 'image' && preview.inline_safe && preview.size <= 10_000_000) {
        if (imageUrl.current) URL.revokeObjectURL(imageUrl.current);
        image = imageUrl.current = URL.createObjectURL(await api.fetchBlob(space.root, entry.path, true));
      }
      setSeen({ entry, preview, image });
    } catch (e) { setSeen({ entry, error: e instanceof Error ? e.message : String(e) }); }
  };
  const download = (e: Entry) => void run(async () => {
    const url = URL.createObjectURL(await api.fetchBlob(space.root, e.path));
    const a = document.createElement('a');
    a.href = url; a.download = e.name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }, `Could not download ${e.name}`);
  const upload = async (files: FileList | null) => {
    setUploadError('');
    for (const f of Array.from(files ?? [])) {
      setProgress({ name: f.name, done: 0, total: f.size });
      try { await api.upload(f, space.root, dir, (done) => setProgress({ name: f.name, done, total: f.size })); }
      catch (e) { setUploadError(`${f.name}: ${e instanceof Error ? e.message : String(e)}`); break; }
    }
    setProgress(undefined); if (input.current) input.current.value = '';
    void entries.reload(); onChanged();
  };
  const files = (entries.data ?? []);
  return <Card title={space.name} aside={<span className="om-hint">{human(space.used_bytes)} used{space.quota_bytes ? ` of ${human(space.quota_bytes)}` : ''}{space.free_bytes !== null ? ` · ${human(space.free_bytes)} free on the box` : ''}</span>}>
    <nav aria-label="Folder path">
      <Button size="sm" variant="ghost" onClick={() => setDir(space.path)}>{space.name}</Button>
      {crumbs.map((c, i) => <span key={i}> / <Button size="sm" variant="ghost" onClick={() => setDir('/' + crumbs.slice(0, i + 1).join('/'))}>{c}</Button></span>)}
    </nav>
    <div role="toolbar" aria-label="Folder actions">
      {dir !== space.path && <Button size="sm" variant="secondary" onClick={() => setDir(parent(dir))}>Up one folder</Button>}
      <Button size="sm" variant="secondary" onClick={() => void entries.reload()}>Refresh files</Button>
      {space.writable ? <>
        <Button size="sm" onClick={() => input.current?.click()} disabled={!!progress}>Upload files</Button>
        <Button size="sm" variant="secondary" onClick={() => { setName(''); setFolderOpen(true); }}>New folder</Button>
      </> : <span className="om-hint">Read-only here.</span>}
      <input ref={input} type="file" multiple hidden aria-label="Choose files to upload" onChange={(e) => void upload(e.target.files)} />
    </div>
    {progress && <p role="status">Uploading {progress.name}: {human(progress.done)} of {human(progress.total)}</p>}
    {uploadError && <p role="alert">{uploadError}</p>}
    {entries.error && entries.data !== undefined && <p role="status">Could not refresh. Showing the folder as last fetched.</p>}
    <Load res={entries} what="Loading folder">{() => files.length === 0 ? <p>This folder is empty.</p> : <table className="om-table">
      <thead><tr><th scope="col">Name</th><th scope="col">Size</th><th scope="col">Modified</th><th scope="col">Actions</th></tr></thead>
      <tbody>{files.map((e) => <tr key={e.path}>
        <td><Button size="sm" variant="ghost" aria-label={`${e.type === 'dir' ? 'Open folder' : 'Preview'} ${e.name}`} onClick={() => open(e)}>{e.type === 'dir' ? '📁 ' : ''}{e.name}</Button></td>
        <td>{e.type === 'dir' ? '' : human(e.size)}</td><td>{when(e.mtime)}</td>
        <td>{e.type !== 'dir' && <Button size="sm" variant="secondary" aria-label={`Download ${e.name}`} onClick={() => download(e)}>Download</Button>}{' '}
          {space.writable && <Button size="sm" variant="secondary" aria-label={`Move ${e.name} to trash`} onClick={() => setDoomed(e)}>Move to trash</Button>}</td>
      </tr>)}</tbody>
    </table>}</Load>
    {files.length > 0 && <FilesFooter entries={files} />}
    {space.writable && <FilesDropZone busy={!!progress} onFiles={(f) => void upload(f)} />}
    {seen && <Card as="article" title={`Preview: ${seen.entry.name}`} variant="sunken" aside={<Button size="sm" variant="ghost" onClick={() => setSeen(undefined)}>Close preview</Button>}>
      {seen.error ? <p role="alert">{seen.error}</p> : !seen.preview ? <p role="status">Loading preview…</p> : <>
        <dl className="om-facts"><div><dt>Type</dt><dd>{seen.preview.mime}</dd></div><div><dt>Size</dt><dd>{human(seen.preview.size)}</dd></div>
          {seen.preview.image && <div><dt>Dimensions</dt><dd>{seen.preview.image.width} × {seen.preview.image.height}</dd></div>}</dl>
        {seen.image && <img src={seen.image} alt={seen.entry.name} style={{ maxWidth: '100%', maxHeight: 360 }} />}
        {seen.preview.text && <><pre tabIndex={0} aria-label="Start of the file">{seen.preview.text.excerpt}</pre>{seen.preview.text.truncated && <p className="om-hint">Only the start of the file is shown.</p>}</>}
        {!seen.image && !seen.preview.text && <p className="om-hint">No preview for this type. Download it to open it.</p>}
      </>}
    </Card>}
    <Dialog open={folderOpen} onClose={() => setFolderOpen(false)} title="New folder" description={`Created in ${dir}.`}
      actions={<Button disabled={!name.trim() || name.includes('/')} onClick={() => void run(async () => { await api.mkdir(space.root, dir === '/' ? `/${name.trim()}` : `${dir}/${name.trim()}`); setFolderOpen(false); await entries.reload(); }, 'Could not create the folder')}>Create folder</Button>}>
      <TextField id="files-new-folder" label="Folder name" value={name} onChange={setName} />
    </Dialog>
    <Dialog role="alertdialog" open={!!doomed} onClose={() => setDoomed(undefined)} title={`Move ${doomed?.name ?? ''} to the trash?`} description="It stays in the trash and can be restored until the trash is emptied or its retention ends."
      actions={<Button onClick={() => void run(async () => { await api.trash(space.root, doomed!.path); setDoomed(undefined); setSeen(undefined); await entries.reload(); onChanged(); }, 'Could not move to the trash')}>Move to trash</Button>}>
      <p>{doomed?.path}</p>
    </Dialog>
  </Card>;
}

function TrashTab({ api, run }: { api: FilesApi; run: Run }) {
  const [which, setWhich] = useState<'home' | 'shared'>('home');
  const items = usePoll(() => api.trashList(which), 30_000);
  const key = useRef<{ which: string; key: string } | undefined>(undefined);
  const [filed, setFiled] = useState('');
  const [confirm, setConfirm] = useState(false);
  useEffect(() => { void items.reload(); }, [which]); // eslint-disable-line react-hooks/exhaustive-deps
  const ask = () => void run(async () => {
    if (key.current?.which !== which) key.current = { which, key: uuid4() };
    const r = (await api.requestTrashEmpty(which, key.current.key)) as { id?: string };
    key.current = undefined; setConfirm(false); setFiled(String(r.id ?? ''));
  }, 'Could not file the request');
  return <Card title="Trash">
    <div role="group" aria-label="Which trash">
      {(['home', 'shared'] as const).map((w) => <Button key={w} size="sm" variant={which === w ? 'primary' : 'secondary'} aria-pressed={which === w} onClick={() => setWhich(w)}>{w === 'home' ? 'My trash' : 'Shared trash'}</Button>)}
      <Button size="sm" variant="secondary" onClick={() => setConfirm(true)}>Ask to empty this trash</Button>
    </div>
    {filed && <p role="status">Request {filed} filed. Nothing is deleted until a person approves it in the Sharing tab.</p>}
    <Load res={items} what="Loading the trash">{(rows: TrashItem[]) => rows.length === 0 ? <p>The trash is empty.</p> : <ul>
      {rows.map((t) => <li key={t.id}><strong>{t.name}</strong> from {t.path} · {human(t.size)} · trashed {when(t.trashed_at)} · deleted for good {when(t.purge_at)}{' '}
        <Button size="sm" variant="secondary" aria-label={`Restore ${t.name}`} onClick={() => void run(async () => { await api.restore(t.id); await items.reload(); }, `Could not restore ${t.name}`)}>Restore</Button></li>)}
    </ul>}</Load>
    <Dialog role="alertdialog" open={confirm} onClose={() => setConfirm(false)} title="Ask to empty the trash for good" description="This files a request. Nothing is deleted until it is approved, and what it deletes is shown to the approver first."
      actions={<Button onClick={ask}>File the request</Button>}><p>Trash: {which === 'home' ? 'mine' : 'shared'}.</p></Dialog>
  </Card>;
}

function Sharing({ api, run, person, roots }: { api: FilesApi; run: Run; person: string; roots: FileRoot[] }) {
  const grants = usePoll(() => api.grants(), 30_000);
  const reqs = usePoll(() => api.requests(), 15_000);
  const [form, setForm] = useState(false);
  const [subject, setSubject] = useState<'app' | 'agent'>('app');
  const [subjectId, setSubjectId] = useState('');
  const [rootId, setRootId] = useState(roots[0]?.root ?? 'shared');
  const [path, setPath] = useState('/');
  const [access, setAccess] = useState<'r' | 'rw'>('r');
  const [reason, setReason] = useState('');
  const [deciding, setDeciding] = useState<FileRequest>();
  const pending = useRef<string | undefined>(undefined);
  const reload = () => { void grants.reload(); void reqs.reload(); };
  const send = () => void run(async () => {
    pending.current ??= uuid4();
    await api.requestGrant({ subject: { kind: subject, id: subjectId.trim() }, root: rootId, path, access, ...(reason.trim() ? { reason: reason.trim() } : {}) }, pending.current);
    pending.current = undefined; setForm(false); reload();
  }, 'Could not file the request');
  const decide = (r: FileRequest, how: 'approve' | 'deny' | 'cancel') => void run(async () => {
    await (how === 'approve' ? api.approve(r) : how === 'deny' ? api.deny(r.id) : api.cancel(r.id));
    setDeciding(undefined); reload();
  }, `Could not ${how} the request`);
  return <>
    <Card title="Who can reach these files" aside={<Button size="sm" onClick={() => { pending.current = undefined; setForm(true); }}>Request folder access</Button>}>
      <Load res={grants} what="Loading grants">{(rows) => rows.length === 0 ? <p>No app or agent has folder access.</p> : <ul>
        {rows.map((g) => <li key={g.id}><strong>{g.subject.kind} {g.subject.id}</strong> · {g.access === 'rw' ? 'read and write' : 'read only'} · {g.root}:{g.path}{' '}
          <Button size="sm" variant="secondary" aria-label={`Revoke access for ${g.subject.id}`} onClick={() => void run(async () => { await api.revoke(g.id); reload(); }, 'Could not revoke')}>Revoke</Button></li>)}
      </ul>}</Load>
    </Card>
    <Card title="Requests">
      <Load res={reqs} what="Loading requests">{(rows) => rows.length === 0 ? <p>No file requests.</p> : <ul>
        {rows.map((r) => <li key={r.id}><StatusPill tone={r.state === 'awaiting_approval' ? 'warn' : 'neutral'} label={r.state.replace('_', ' ')} /> {r.plan.summary ?? r.type}
          {r.reason ? ` · "${r.reason}"` : ''} · risk {r.risk} · asked by {r.requested_by.id} · expires {when(r.expires_at)}{' '}
          {r.state === 'awaiting_approval' && <>
            <Button size="sm" aria-label={`Review request ${r.id}`} onClick={() => setDeciding(r)}>Review</Button>{' '}
            {r.requested_by.id === person && <Button size="sm" variant="secondary" aria-label={`Cancel request ${r.id}`} onClick={() => decide(r, 'cancel')}>Cancel request</Button>}</>}</li>)}
      </ul>}</Load>
    </Card>
    <Dialog open={form} onClose={() => setForm(false)} title="Request folder access" description="This files a request. The app or agent gets nothing until a person approves it."
      actions={<Button disabled={!subjectId.trim()} onClick={send}>File the request</Button>}>
      <label htmlFor="grant-kind">Gives access to</label>
      <select id="grant-kind" value={subject} onChange={(e) => setSubject(e.target.value as 'app' | 'agent')}><option value="app">An app</option><option value="agent">An agent</option></select>
      <TextField id="grant-subject" label={subject === 'app' ? 'App id' : 'Agent id'} value={subjectId} onChange={setSubjectId} />
      <label htmlFor="grant-root">Space</label>
      <select id="grant-root" value={rootId} onChange={(e) => setRootId(e.target.value)}>{roots.filter((r) => r.kind !== 'grant').map((r) => <option key={r.root} value={r.root}>{r.name}</option>)}</select>
      <TextField id="grant-path" label="Folder" value={path} onChange={setPath} />
      <label htmlFor="grant-access">Access</label>
      <select id="grant-access" value={access} onChange={(e) => setAccess(e.target.value as 'r' | 'rw')}><option value="r">Read only</option><option value="rw">Read and write</option></select>
      <TextField id="grant-reason" label="Reason (optional)" value={reason} onChange={setReason} />
    </Dialog>
    <Dialog role="alertdialog" open={!!deciding} onClose={() => setDeciding(undefined)} title="Review this request" description="Approving applies exactly this plan. If it changed since you opened it, the hub refuses."
      actions={<><Button variant="secondary" onClick={() => decide(deciding!, 'deny')}>Deny</Button><Button onClick={() => decide(deciding!, 'approve')}>Approve this plan</Button></>}>
      <p>{deciding?.plan.summary}</p><p className="om-hint">Risk: {deciding?.risk}. Plan {deciding?.plan_sha256.slice(0, 19)}…</p>
    </Dialog>
  </>;
}
