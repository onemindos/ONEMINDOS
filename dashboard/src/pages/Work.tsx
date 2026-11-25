// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState, type FormEvent } from 'react';
import { OneMind, OneMindError, type operations } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn } from '../session';

type Task = operations['work.task_get']['responses'][200]['content']['application/json'];
type Capture = operations['work.capture']['requestBody']['content']['application/json'];

function WorkList({ client }: { client: OneMind }) {
  const [title, setTitle] = useState('');
  const [key, setKey] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState('');
  const tasks = usePoll(async () => {
    try {
      return { rows: await client.call<Task[]>({ method: 'GET', path: '/v1/work/tasks' }) };
    } catch (error) {
      if (error instanceof OneMindError && (error.status === 401 || error.status === 403)) {
        return { denied: true } as const;
      }
      throw error;
    }
  }, 5000);

  async function capture(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !title.trim()) return;
    const attempt = key ?? uuidv4();
    setKey(attempt);
    setSaving(true);
    setProblem('');
    try {
      const body: Capture = { title: title.trim(), body: "", labels: [], priority: 4, status: "todo" };
      await client.call<Task>({
        method: 'POST', path: '/v1/work/capture', body, headers: { 'Idempotency-Key': attempt },
      });
      setTitle('');
      setKey(undefined);
      await tasks.reload();
    } catch (error) {
      setProblem(error instanceof OneMindError && error.status === 403
        ? 'Your account cannot save Work tasks.' : 'The task could not be saved. You can retry.');
    } finally {
      setSaving(false);
    }
  }

  if (tasks.data?.denied) return <p role="status">Your account does not have access to Work.</p>;
  return (
    <Card title="Tasks">
      <form className="dash-actions" onSubmit={(event) => void capture(event)}>
        <label>Task <input value={title} maxLength={160} required disabled={saving}
          onChange={(event) => { setTitle(event.target.value); setKey(undefined); }} /></label>
        <Button type="submit" disabled={saving || !title.trim()}>Add to Inbox</Button>
      </form>
      {problem && <p role="status">{problem}</p>}
      {tasks.loading && <p role="status">Loading tasks…</p>}
      {tasks.error && <p role="status">The gateway could not load your tasks.</p>}
      {tasks.data?.rows?.length === 0 && <p>No tasks yet.</p>}
      {tasks.data?.rows && tasks.data.rows.length > 0 && (
        <ul>{tasks.data.rows.map((task) => (
          <li key={task.id}>
            <strong>{task.title}</strong>{task.status === 'done' && ' · Done'}
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
