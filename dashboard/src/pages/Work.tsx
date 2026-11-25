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
            {task.repeat && <> · repeats every {task.repeat.interval > 1 ? `${task.repeat.interval} ` : ''}{task.repeat.every}</>}
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
