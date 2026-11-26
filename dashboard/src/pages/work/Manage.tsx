// SPDX-License-Identifier: Apache-2.0
// Work writes that had a route and no screen: projects (create, rename, who the AI may let see it,
// delete) and one task's edit and delete. Every task write sends the revision the page last read in
// If-Match, so a task changed meanwhile is refused (409) and reloaded rather than overwritten.
import { useState, type FormEvent } from 'react';
import { OneMind, OneMindError, type operations } from '@onemind/sdk';
import { Button, Card, Dialog } from '@onemind/ui';
import { usePoll } from '../../lib/hooks';
import { uuidv4 } from '../../lib/uuid';

type Task = operations['work.task_get']['responses'][200]['content']['application/json'];
type Project = operations['work.projects_list']['responses'][200]['content']['application/json'][number];
const ACCESS = [
  { id: 'none', label: 'The AI cannot see it' },
  { id: 'read', label: 'The AI can read it' },
  { id: 'work', label: 'The AI can read it and work in it' },
] as const;
type Access = (typeof ACCESS)[number]['id'];
const accessWord = (a: string) => ACCESS.find((x) => x.id === a)?.label ?? a;

function why(e: unknown, fallback: string): string {
  if (e instanceof OneMindError) {
    if (e.status === 409) return 'That changed meanwhile. It has been reloaded; try again.';
    if (e.status === 403) return 'Only the person who made it can do that.';
    if (e.status === 422) return 'That was not accepted. Check the name and the values.';
  }
  return fallback;
}
const toLocal = (iso: string | null | undefined) => {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

export function TaskTools({ client, task, onChanged }: { client: OneMind; task: Task; onChanged: () => Promise<void> | void }) {
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [due, setDue] = useState(toLocal(task.due_at));
  const [priority, setPriority] = useState(String(task.priority));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const path = `/v1/work/projects/${encodeURIComponent(task.project_id)}/tasks/${encodeURIComponent(task.id)}` as const;
  const headers = { 'If-Match': String(task.revision) };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || !title.trim()) return;
    setBusy(true); setError('');
    try {
      await client.call<Task>({ method: 'PATCH', path, headers, body: { title: title.trim(), priority: Number(priority), due_at: due ? new Date(due).toISOString() : null } });
      setEditing(false); await onChanged();
    } catch (err) { setError(why(err, 'The task could not be saved. You can retry.')); if (err instanceof OneMindError && err.status === 409) { setEditing(false); await onChanged(); } }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (busy) return;
    setBusy(true); setError('');
    try { await client.call<unknown>({ method: 'DELETE', path, headers }); setDeleting(false); await onChanged(); }
    catch (err) { setError(why(err, 'The task could not be deleted. You can retry.')); if (err instanceof OneMindError && err.status === 409) { setDeleting(false); await onChanged(); } }
    finally { setBusy(false); }
  };
  return <>
    {' '}<Button type="button" size="sm" variant="secondary" onClick={() => { setError(''); setEditing((v) => !v); }} aria-label={`Edit ${task.title}`}>Edit</Button>
    {' '}<Button type="button" size="sm" variant="ghost" onClick={() => { setError(''); setDeleting(true); }} aria-label={`Delete ${task.title}`}>Delete</Button>
    {editing && <form aria-label={`Edit ${task.title}`} onSubmit={(e) => void save(e)}>
      <p><label htmlFor={`t-title-${task.id}`}>Title</label>{' '}<input id={`t-title-${task.id}`} className="om-input" value={title} maxLength={160} required onChange={(e) => setTitle(e.target.value)} /></p>
      <p><label htmlFor={`t-due-${task.id}`}>Due</label>{' '}<input id={`t-due-${task.id}`} type="datetime-local" className="om-input" value={due} onChange={(e) => setDue(e.target.value)} />{' '}
        <span className="om-note">Empty means no due time.</span></p>
      <p><label htmlFor={`t-pri-${task.id}`}>How urgent</label>{' '}<select id={`t-pri-${task.id}`} className="om-input" value={priority} onChange={(e) => setPriority(e.target.value)}>
        <option value="1">1, most urgent</option><option value="2">2</option><option value="3">3</option><option value="4">4, normal</option></select></p>
      {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
      <Button type="submit" disabled={busy || !title.trim()}>{busy ? 'Saving…' : 'Save task'}</Button>{' '}
      <Button type="button" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>Cancel</Button>
    </form>}
    <Dialog open={deleting} role="alertdialog" title={`Delete "${task.title}"?`} onClose={() => { if (!busy) setDeleting(false); }} actions={<Button disabled={busy} onClick={() => void remove()}>{busy ? 'Deleting…' : 'Yes, delete it'}</Button>}>
      <p>The task and its notes are removed for everyone in the project. This cannot be undone.</p>
      {error && <p role="alert">{error}</p>}
    </Dialog>
  </>;
}

export function Projects({ client, onChanged }: { client: OneMind; onChanged: () => Promise<void> | void }) {
  const list = usePoll(async () => client.call<Project[]>({ method: 'GET', path: '/v1/work/projects' }), 30_000);
  const [name, setName] = useState('');
  const [access, setAccess] = useState<Access>('none');
  const [key, setKey] = useState<string>();
  const [editing, setEditing] = useState<{ id: string }>();
  const [deleting, setDeleting] = useState<Project>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async (fn: () => Promise<unknown>, fallback: string) => {
    if (busy) return false;
    setBusy(true); setError('');
    try { await fn(); await list.reload(); await onChanged(); return true; }
    catch (e) { setError(why(e, fallback)); return false; }
    finally { setBusy(false); }
  };
  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    const attempt = key ?? uuidv4();
    setKey(attempt);
    if (await run(() => client.call<Project>({ method: 'POST', path: '/v1/work/projects', body: { name: name.trim(), ai_access: access }, headers: { 'Idempotency-Key': attempt } }), 'The project could not be created. You can retry.')) { setName(''); setKey(undefined); }
  };
  const rows = list.data;
  return <Card title="Projects">
    <form className="dash-actions" aria-label="New project" onSubmit={(e) => void create(e)}>
      <label>New project <input className="om-input" value={name} maxLength={160} required placeholder="Home" onChange={(e) => { setName(e.target.value); setKey(undefined); }} /></label>{' '}
      <label>AI access <select className="om-input" value={access} onChange={(e) => { setAccess(e.target.value as Access); setKey(undefined); }}>{ACCESS.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}</select></label>{' '}
      <Button type="submit" disabled={busy || !name.trim()}>Create project</Button>
    </form>
    {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
    {list.error && !rows && <p role="status">The projects could not be loaded.</p>}
    {rows && rows.length === 0 && <p>No projects yet. A project holds a group of tasks, such as Home or Garden.</p>}
    {rows && rows.length > 0 && <ul aria-label="Projects">{rows.map((p) => <li key={p.id}>
      {editing?.id === p.id
        ? <RenameForm project={p} busy={busy} onCancel={() => setEditing(undefined)} onSave={(n, ac) => void run(() => client.call<Project>({ method: 'PATCH', path: `/v1/work/projects/${encodeURIComponent(p.id)}`, body: { name: n, ai_access: ac } }), 'The project could not be saved. You can retry.').then((ok) => { if (ok) setEditing(undefined); })} />
        : <><strong>{p.name}</strong> · {accessWord(p.ai_access)}{' '}
          <Button size="sm" variant="secondary" aria-label={`Edit project ${p.name}`} onClick={() => { setError(''); setEditing({ id: p.id }); }}>Edit</Button>{' '}
          <Button size="sm" variant="ghost" aria-label={`Delete project ${p.name}`} onClick={() => { setError(''); setDeleting(p); }}>Delete</Button></>}
    </li>)}</ul>}
    <Dialog open={!!deleting} role="alertdialog" title={`Delete the project "${deleting?.name}"?`} onClose={() => { if (!busy) setDeleting(undefined); }}
      actions={<Button disabled={busy} onClick={() => deleting && void run(() => client.call<unknown>({ method: 'DELETE', path: `/v1/work/projects/${encodeURIComponent(deleting.id)}` }), 'The project could not be deleted. You can retry.').then((ok) => { if (ok) setDeleting(undefined); })}>{busy ? 'Deleting…' : 'Yes, delete the project'}</Button>}>
      <p>Every task in it is deleted too, for everyone in the project. This cannot be undone. Only the person who made the project can do this.</p>
      {error && <p role="alert">{error}</p>}
    </Dialog>
  </Card>;
}

function RenameForm({ project, busy, onSave, onCancel }: { project: Project; busy: boolean; onSave: (name: string, access: Access) => void; onCancel: () => void }) {
  const [name, setName] = useState(project.name);
  const [access, setAccess] = useState<Access>(project.ai_access as Access);
  return <form aria-label={`Rename ${project.name}`} onSubmit={(e) => { e.preventDefault(); if (name.trim()) onSave(name.trim(), access); }}>
    <label>Name <input className="om-input" value={name} maxLength={160} required onChange={(e) => setName(e.target.value)} /></label>{' '}
    <label>AI access <select className="om-input" value={access} onChange={(e) => setAccess(e.target.value as Access)}>{ACCESS.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}</select></label>{' '}
    <Button type="submit" size="sm" disabled={busy || !name.trim()}>Save project</Button>{' '}
    <Button type="button" size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
  </form>;
}
