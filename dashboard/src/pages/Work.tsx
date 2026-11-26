// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { OneMind, OneMindError, type operations } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn } from '../session';

type Task = operations['work.task_get']['responses'][200]['content']['application/json'];
type QuickAdd = operations['work.quick_add']['requestBody']['content']['application/json'];

const VIEWS = [
  { id: 'today', label: 'Today', empty: 'Nothing due today.' },
  { id: 'upcoming', label: 'Upcoming', empty: 'Nothing coming up.' },
  { id: 'inbox', label: 'Inbox', empty: 'Your Inbox is empty.' },
  { id: 'all', label: 'All', empty: 'No tasks yet.' },
] as const;
type View = (typeof VIEWS)[number]['id'];

const zoneName = Intl.DateTimeFormat().resolvedOptions().timeZone;
const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });

const ZONES: string[] = (() => {
  try {
    return (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.('timeZone') ?? [];
  } catch {
    return [];
  }
})();

/** The time zone a repeating task counts its days in ("every weekday" skips that zone's weekend). */
function RepeatZone({ client, task, onSaved }: { client: OneMind; task: Task; onSaved: () => Promise<void> | void }) {
  const rule = task.repeat!;
  const current = rule.tz ?? 'UTC';
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(current);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const zone = draft.trim();
    if (busy || !zone) return;
    setBusy(true);
    setProblem('');
    try {
      await client.call<Task>({
        method: 'PATCH', path: `/v1/work/projects/${encodeURIComponent(task.project_id)}/tasks/${encodeURIComponent(task.id)}`,
        body: { repeat: { every: rule.every, interval: rule.interval, tz: zone } }, headers: { 'If-Match': String(task.revision) },
      });
      setOpen(false);
      await onSaved();
    } catch (error) {
      setProblem(error instanceof OneMindError && error.status === 422 ? 'That time zone is not known. Use a name such as Europe/Paris.'
        : error instanceof OneMindError && error.status === 409 ? 'That task changed meanwhile. Reload and try again.'
          : 'The time zone could not be saved. You can retry.');
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return <> ({current}) <Button type="button" onClick={() => { setDraft(current); setOpen(true); }} aria-label={`Change repeat time zone of ${task.title}`}>Zone</Button></>;
  }
  return (
    <form className="dash-actions" onSubmit={(event) => void save(event)}>
      <label>Repeat time zone <input value={draft} list="work-zones" maxLength={64} required disabled={busy} onChange={(event) => setDraft(event.target.value)} /></label>
      <datalist id="work-zones">{ZONES.map((z) => <option key={z} value={z} />)}</datalist>
      <Button type="submit" disabled={busy || !draft.trim()}>Save zone</Button>
      <Button type="button" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button>
      {problem && <span role="status">{problem}</span>}
    </form>
  );
}

function WorkList({ client }: { client: OneMind }) {
  const [view, setView] = useState<View>('today');
  const [text, setText] = useState('');
  const [key, setKey] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState('');
  const tasks = usePoll(async () => {
    try {
      const rows = await client.call<Task[]>({ method: 'GET', path: `/v1/work/tasks?view=${view}&tz=${encodeURIComponent(zoneName)}` });
      return { view, rows };
    } catch (error) {
      if (error instanceof OneMindError && (error.status === 401 || error.status === 403)) return { view, denied: true } as const;
      throw error;
    }
  }, 5000);
  const reload = tasks.reload;
  useEffect(() => { void reload(); }, [view, reload]);

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !text.trim()) return;
    const attempt = key ?? uuidv4();
    setKey(attempt);
    setSaving(true);
    setProblem('');
    try {
      const body: QuickAdd = { text: text.trim(), tz: zoneName };
      await client.call<Task>({ method: 'POST', path: '/v1/work/quick-add', body, headers: { 'Idempotency-Key': attempt } });
      setText('');
      setKey(undefined);
      await tasks.reload();
    } catch (error) {
      setProblem(error instanceof OneMindError && error.status === 403 ? 'Your account cannot save Work tasks.'
        : error instanceof OneMindError && error.status === 422 ? 'That line could not be read. Check the project name and the date.'
          : 'The task could not be saved. You can retry.');
    } finally {
      setSaving(false);
    }
  }

  async function finish(task: Task) {
    setProblem('');
    try {
      await client.call<Task>({
        method: 'PATCH', path: `/v1/work/projects/${encodeURIComponent(task.project_id)}/tasks/${encodeURIComponent(task.id)}`,
        body: { status: 'done' }, headers: { 'If-Match': String(task.revision) },
      });
      await tasks.reload();
    } catch (error) {
      setProblem(error instanceof OneMindError && error.status === 409
        ? 'That task changed meanwhile. It has been reloaded.' : 'The task could not be completed. You can retry.');
      await tasks.reload();
    }
  }

  const current = VIEWS.find((v) => v.id === view)!;
  const rows = tasks.data?.view === view ? tasks.data.rows : undefined;
  if (tasks.data?.denied) return <p role="status">Your account does not have access to Work.</p>;
  return (
    <Card title="Tasks">
      <form className="dash-actions" onSubmit={(event) => void add(event)}>
        <label>Quick add <input value={text} maxLength={400} required disabled={saving} placeholder="Pay rent tomorrow at 5pm #Home @bills p1"
          onChange={(event) => { setText(event.target.value); setKey(undefined); }} /></label>
        <Button type="submit" disabled={saving || !text.trim()}>Add</Button>
      </form>
      <div role="group" aria-label="Task view" className="dash-actions">
        {VIEWS.map((v) => (
          <Button key={v.id} type="button" aria-pressed={v.id === view} onClick={() => setView(v.id)}>{v.label}</Button>
        ))}
      </div>
      {problem && <p role="status">{problem}</p>}
      {tasks.loading && !rows && <p role="status">Loading tasks…</p>}
      {tasks.error && <p role="status">The gateway could not load your tasks.</p>}
      {rows?.length === 0 && <p>{current.empty}</p>}
      {rows && rows.length > 0 && (
        <ul>{rows.map((task) => (
          <li key={`${task.project_id}/${task.id}`}>
            <strong>{task.title}</strong>
            {task.due_at && <> · due {when(task.due_at)}</>}
            {task.repeat && <> · repeats every {task.repeat.interval > 1 ? `${task.repeat.interval} ` : ''}{task.repeat.every}<RepeatZone client={client} task={task} onSaved={tasks.reload} /></>}
            {task.priority < 4 && <> · p{task.priority}</>}
            {task.labels.length > 0 && <> · {task.labels.map((l) => `@${l}`).join(' ')}</>}
            {task.status === 'done' ? ' · Done' : <> <Button type="button" onClick={() => void finish(task)}>Done</Button></>}
          </li>
        ))}</ul>
      )}
    </Card>
  );
}

export function Work() {
  const { token, person, mock } = useSignedIn();
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  return (
    <div className="dash-stack">
      <PageHeader title="Work" />
      {mock ? <p>Connect to a hub to open Work.</p> : <WorkList key={person} client={client} />}
    </div>
  );
}
