// SPDX-License-Identifier: Apache-2.0
import { useState, type FormEvent } from 'react';
import { Button } from '@onemind/ui';
import { type OneMind, type components } from '@onemind/sdk';
import { usePoll } from '../../lib/hooks';
import { explain } from '../../lib/permissions';
import { uuidv4 } from '../../lib/uuid';
import { useSignedIn } from '../../session';
import { Load } from '../parts';

type Project = components['schemas']['Project'];
type Task = components['schemas']['Task'];
type Comment = components['schemas']['Comment'];
type Section = components['schemas']['Section'];
type Activity = components['schemas']['Activity'];

function useMutation(reload: () => void | Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const run = async (send: () => Promise<unknown>, after?: () => void) => {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try { await send(); after?.(); await reload(); }
    catch (e) { setError(explain(e)); }
    finally { setBusy(false); }
  };
  return { busy, error, run };
}

function useDraft() {
  const [value, setValue] = useState('');
  const [key, setKey] = useState<string>();
  return {
    value,
    change: (next: string) => { setValue(next); setKey(undefined); },
    headers: () => {
      const attempt = key ?? uuidv4();
      setKey(attempt);
      return { 'Idempotency-Key': attempt };
    },
  };
}

export function TaskDetails({ client, task }: { client: OneMind; task: Task }) {
  const [open, setOpen] = useState(false);
  return <>
    {' '}<Button size="sm" variant="ghost" aria-expanded={open} aria-label={`Discussion and activity for ${task.title}`}
      onClick={() => setOpen(!open)}>Discussion</Button>
    {open && <Discussion client={client} task={task} />}
  </>;
}

function Discussion({ client, task }: { client: OneMind; task: Task }) {
  const { principal } = useSignedIn();
  const project = encodeURIComponent(task.project_id);
  const id = encodeURIComponent(task.id);
  const details = usePoll(async () => {
    const [comments, activity] = await Promise.all([
      client.call<Comment[]>({ method: 'GET', path: `/v1/work/projects/${project}/tasks/${id}/comments` }),
      client.call<Activity[]>({ method: 'GET', path: `/v1/work/projects/${project}/tasks/${id}/activity` }),
    ]);
    return { comments, activity };
  }, 0);
  const note = useDraft();
  const { busy, error, run } = useMutation(details.reload);

  return <Load res={details} what="Loading task discussion">
    {({ comments, activity }) => <>
      <h3>Comments</h3>
      {comments.length === 0 ? <p>No comments yet.</p> : <ul aria-label="Comments">
        {comments.map((comment) => <li key={comment.id}>
          <span>{comment.body}</span>{' '}<small>{comment.author_id}</small>{' '}
          {principal?.id === comment.author_id && <Button size="sm" variant="ghost" disabled={busy} aria-label={`Delete comment: ${comment.body}`}
            onClick={() => void run(() => client.call<void>({
              method: 'DELETE', path: `/v1/work/projects/${project}/tasks/${id}/comments/${encodeURIComponent(comment.id)}`,
            }))}>Delete</Button>}
        </li>)}
      </ul>}
      <form className="dash-actions" onSubmit={(e) => {
        e.preventDefault();
        if (note.value.trim()) void run(() => client.call<Comment>({
          method: 'POST', path: `/v1/work/projects/${project}/tasks/${id}/comments`,
          body: { body: note.value.trim() }, headers: note.headers(),
        }), () => note.change(''));
      }}>
        <label>Comment <input required maxLength={5000} disabled={busy} value={note.value} onChange={(e) => note.change(e.target.value)} /></label>
        <Button type="submit" disabled={busy || !note.value.trim()}>Post comment</Button>
      </form>
      {error && <p role="alert">{error}</p>}
      <h3>Activity</h3>
      {activity.length === 0 ? <p>No activity yet.</p> : <ul aria-label="Task activity">
        {activity.map((entry) => <li key={entry.id}>
          {entry.actor_id} {entry.kind} {entry.fields.join(', ')} · {new Date(entry.at).toLocaleString()}
        </li>)}
      </ul>}
    </>}
  </Load>;
}

export function ProjectDetails({ client, project, onChanged }: { client: OneMind; project: Project; onChanged: () => void | Promise<void> }) {
  const [open, setOpen] = useState(false);
  return <>
    {' '}<Button size="sm" variant="ghost" aria-label={`Details for ${project.name}`} aria-expanded={open}
      onClick={() => setOpen(!open)}>Details</Button>
    {open && <ProjectContents client={client} projectId={project.id} onChanged={onChanged} />}
  </>;
}

function ProjectContents({ client, projectId, onChanged }: { client: OneMind; projectId: string; onChanged: () => void | Promise<void> }) {
  const id = encodeURIComponent(projectId);
  const contents = usePoll(async () => {
    const [project, members, sections] = await Promise.all([
      client.call<Project>({ method: 'GET', path: `/v1/work/projects/${id}` }),
      client.call<string[]>({ method: 'GET', path: `/v1/work/projects/${id}/members` }),
      client.call<Section[]>({ method: 'GET', path: `/v1/work/projects/${id}/sections` }),
    ]);
    return { project, members, sections };
  }, 0);
  const title = useDraft();
  const newSection = useDraft();
  const [sectionId, setSectionId] = useState('');
  const [person, setPerson] = useState('');
  const [rename, setRename] = useState<{ id: string; name: string }>();
  const { busy, error, run } = useMutation(async () => { await contents.reload(); await onChanged(); });

  const capture = (e: FormEvent) => {
    e.preventDefault();
    if (title.value.trim()) void run(() => client.call<Task>({
      method: 'POST', path: '/v1/work/capture',
      body: { title: title.value.trim(), project_id: projectId, section_id: sectionId || null },
      headers: title.headers(),
    }), () => { title.change(''); setSectionId(''); });
  };

  return <Load res={contents} what="Loading project details">
    {({ project, members, sections }) => <section aria-label={`Project details for ${project.name}`}>
      <h3>People</h3>
      <ul aria-label="Project members">{members.map((member) => <li key={member}>{member}{' '}
        <Button size="sm" variant="ghost" disabled={busy} aria-label={`Remove ${member} from the project`}
          onClick={() => void run(() => client.call<void>({
            method: 'DELETE', path: `/v1/work/projects/${id}/members/${encodeURIComponent(member)}`,
          }))}>Remove</Button>
      </li>)}</ul>
      <form className="dash-actions" onSubmit={(e) => {
        e.preventDefault();
        if (person.trim()) void run(() => client.call<void>({
          method: 'PUT', path: `/v1/work/projects/${id}/members/${encodeURIComponent(person.trim())}`,
        }), () => setPerson(''));
      }}>
        <label>Person ID <input required maxLength={128} disabled={busy} value={person} onChange={(e) => setPerson(e.target.value)} /></label>
        <Button type="submit" disabled={busy || !person.trim()}>Add person</Button>
      </form>
      <h3>Sections</h3>
      <ul aria-label="Project sections">{sections.map((section) => <li key={section.id}>
        {rename && rename.id === section.id ? <form className="dash-actions" onSubmit={(e) => {
          e.preventDefault();
          if (rename.name.trim()) void run(() => client.call<Section>({
            method: 'PATCH', path: `/v1/work/projects/${id}/sections/${encodeURIComponent(section.id)}`, body: { name: rename.name.trim() },
          }), () => setRename(undefined));
        }}>
          <label>Section name <input required maxLength={160} disabled={busy} value={rename.name} onChange={(e) => setRename({ ...rename, name: e.target.value })} /></label>
          <Button type="submit" disabled={busy || !rename.name.trim()}>Save section</Button>
          <Button type="button" disabled={busy} onClick={() => setRename(undefined)}>Cancel</Button>
        </form> : <>
          {section.name}{' '}
          <Button size="sm" disabled={busy} onClick={() => setRename(section)} aria-label={`Rename section ${section.name}`}>Rename</Button>{' '}
          <Button size="sm" variant="ghost" disabled={busy} aria-label={`Delete section ${section.name}`}
            onClick={() => void run(() => client.call<void>({
              method: 'DELETE', path: `/v1/work/projects/${id}/sections/${encodeURIComponent(section.id)}`,
            }), () => { if (sectionId === section.id) { setSectionId(''); title.change(title.value); } })}>Delete</Button>
        </>}
      </li>)}</ul>
      <form className="dash-actions" onSubmit={(e) => {
        e.preventDefault();
        if (newSection.value.trim()) void run(() => client.call<Section>({
          method: 'POST', path: `/v1/work/projects/${id}/sections`, body: { name: newSection.value.trim() }, headers: newSection.headers(),
        }), () => newSection.change(''));
      }}>
        <label>New section <input required maxLength={160} disabled={busy} value={newSection.value} onChange={(e) => newSection.change(e.target.value)} /></label>
        <Button type="submit" disabled={busy || !newSection.value.trim()}>Add section</Button>
      </form>
      <h3>New task</h3>
      <form className="dash-actions" onSubmit={capture}>
        <label>Title <input required maxLength={160} disabled={busy} value={title.value} onChange={(e) => title.change(e.target.value)} /></label>
        <label>Section <select disabled={busy} value={sectionId} onChange={(e) => { setSectionId(e.target.value); title.change(title.value); }}>
          <option value="">No section</option>
          {sections.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}
        </select></label>
        <Button type="submit" disabled={busy || !title.value.trim()}>Create task</Button>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>}
  </Load>;
}
