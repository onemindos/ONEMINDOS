// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';

const task = { id: 'tsk_1', project_id: 'prj_1', revision: 3, title: 'Pay rent', body: '', status: 'todo', priority: 4, labels: [], assignee: null,
  due_at: null, section_id: null, repeat: null, dependencies: [], updated_at: '2026-11-25T15:00:00Z' };
const json = (value: unknown, code = 200) => new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } });
type Call = { method: string; path: string; body: Record<string, unknown> | undefined; headers: Headers };

function mount(extra?: (c: Call) => Response | undefined, tasks: () => unknown[] = () => [task], reads?: Call[]) {
  const calls: Call[] = [];
  const projects = [{ id: 'prj_1', name: 'Home', ai_access: 'none' }];
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = new URL(String(url));
    const c: Call = { method: init?.method ?? 'GET', path: u.pathname, body: init?.body ? JSON.parse(String(init.body)) : undefined, headers: new Headers(init?.headers) };
    if (c.method !== 'GET') calls.push(c); else reads?.push(c);
    const custom = extra?.(c);
    if (custom) return custom;
    if (c.method === 'GET' && c.path === '/v1/work/tasks') return json(tasks());
    if (c.method === 'GET' && c.path === '/v1/work/projects') return json(projects);
    if (c.method === 'POST' && c.path === '/v1/work/projects') return json({ id: 'prj_2', name: c.body!.name, ai_access: c.body!.ai_access }, 201);
    if (c.method === 'PATCH' && c.path.endsWith('/tasks/tsk_1')) return json({ ...task, ...c.body, revision: 4 });
    if (c.method === 'PATCH' && c.path === '/v1/work/projects/prj_1') return json({ id: 'prj_1', ...c.body });
    if (c.method === 'DELETE') return new Response(null, { status: 204 });
    return json({ error: 'not_found', message: c.path }, 404);
  }));
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/work']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

it('edits a task with the revision it read in If-Match', async () => {
  const calls = mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Edit Pay rent' }));
  const form = screen.getByRole('form', { name: 'Edit Pay rent' });
  const title = within(form).getByLabelText('Title');
  await u.clear(title); await u.type(title, 'Pay the rent');
  await u.selectOptions(within(form).getByLabelText('How urgent'), '1');
  await u.click(within(form).getByRole('button', { name: 'Save task' }));
  await waitFor(() => expect(calls).toHaveLength(1));
  // Only what changed is sent: the due time was not touched, so it is not in the body.
  expect(calls[0]).toMatchObject({ method: 'PATCH', path: '/v1/work/projects/prj_1/tasks/tsk_1' });
  expect(calls[0]!.body).toEqual({ title: 'Pay the rent', priority: 1 });
  expect(calls[0]!.headers.get('If-Match')).toBe('3');
});

it('keeps the seconds of a due time it did not change, and sends nothing when nothing changed', async () => {
  const calls = mount(undefined, () => [{ ...task, due_at: '2026-12-01T17:00:30Z' }]);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Edit Pay rent' }));
  await u.click(screen.getByRole('button', { name: 'Save task' }));
  expect(await screen.findByText('Nothing was changed.')).toBeInTheDocument();
  expect(calls).toHaveLength(0);
  await u.click(screen.getByRole('button', { name: 'Edit Pay rent' }));
  const title = within(screen.getByRole('form', { name: 'Edit Pay rent' })).getByLabelText('Title');
  await u.type(title, ' now');
  await u.click(screen.getByRole('button', { name: 'Save task' }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0]!.body).toEqual({ title: 'Pay rent now' });
});

it('sends the revision it opened the editor on, so a change from another device is refused, not undone', async () => {
  let current = task;
  const calls = mount((c) => (c.method === 'PATCH' && c.path.endsWith('/tasks/tsk_1')
    ? (c.headers.get('If-Match') === String(current.revision) ? json({ ...current, ...c.body, revision: current.revision + 1 }) : json({ error: 'stale_precondition', message: 'revision' }, 409))
    : undefined), () => [current]);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Edit Pay rent' }));
  await u.selectOptions(within(screen.getByRole('form', { name: 'Edit Pay rent' })).getByLabelText('How urgent'), '1');
  // Another device renames the task; the next read of the list brings revision 4 while the form is open.
  current = { ...task, title: 'Pay rent today', revision: 4 };
  await u.type(screen.getByRole('textbox', { name: 'New project' }), 'Garden');
  await u.click(screen.getByRole('button', { name: 'Create project' }));
  expect(await screen.findByText('Pay rent today')).toBeInTheDocument();
  await u.click(within(screen.getByRole('form', { name: 'Edit Pay rent' })).getByRole('button', { name: 'Save task' }));
  const patch = await waitFor(() => { const p = calls.find((c) => c.method === 'PATCH'); expect(p).toBeDefined(); return p!; });
  expect(patch.headers.get('If-Match')).toBe('3');
  expect(await screen.findByRole('alert')).toHaveTextContent(/changed on another device meanwhile/);
});

it('says the task changed meanwhile on a 409 and reloads instead of overwriting', async () => {
  mount((c) => (c.method === 'PATCH' && c.path.endsWith('/tasks/tsk_1') ? json({ error: 'stale_precondition', message: 'revision' }, 409) : undefined));
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Edit Pay rent' }));
  await u.selectOptions(within(screen.getByRole('form', { name: 'Edit Pay rent' })).getByLabelText('How urgent'), '2');
  await u.click(screen.getByRole('button', { name: 'Save task' }));
  await waitFor(() => expect(screen.queryByRole('form', { name: 'Edit Pay rent' })).not.toBeInTheDocument());
  // The message stays on screen after the form closes.
  expect(screen.getByRole('alert')).toHaveTextContent(/"Pay rent" was changed on another device meanwhile/);
});

it('asks before deleting a task, then deletes once with the revision', async () => {
  const calls = mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Delete Pay rent' }));
  expect(calls).toHaveLength(0);
  const dialog = screen.getByRole('alertdialog');
  expect(dialog).toHaveTextContent(/cannot be undone/);
  await u.click(within(dialog).getByRole('button', { name: 'Yes, delete it' }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0]).toMatchObject({ method: 'DELETE', path: '/v1/work/projects/prj_1/tasks/tsk_1' });
  expect(calls[0]!.headers.get('If-Match')).toBe('3');
});

it('lists projects with plain AI access words and creates one with an idempotency key', async () => {
  const calls = mount();
  const u = userEvent.setup();
  const list = await screen.findByRole('list', { name: 'Projects' });
  expect(within(list).getByText(/The AI cannot see it/)).toBeInTheDocument();
  await u.type(screen.getByRole('textbox', { name: 'New project' }), 'Garden');
  await u.selectOptions(within(screen.getByRole('form', { name: 'New project' })).getByLabelText('AI access'), 'read');
  await u.click(screen.getByRole('button', { name: 'Create project' }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0]).toMatchObject({ method: 'POST', path: '/v1/work/projects', body: { name: 'Garden', ai_access: 'read' } });
  expect(calls[0]!.headers.get('Idempotency-Key')).toMatch(/^[a-f0-9-]{36}$/);
});

it('renames a project and says only its creator may delete it (403)', async () => {
  const calls = mount((c) => (c.method === 'DELETE' && c.path === '/v1/work/projects/prj_1' ? json({ error: 'permission_denied', message: 'creator only' }, 403) : undefined));
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Edit project Home' }));
  const form = screen.getByRole('form', { name: 'Rename Home' });
  const name = within(form).getByLabelText('Name');
  await u.clear(name); await u.type(name, 'House');
  await u.selectOptions(within(form).getByLabelText('AI access'), 'work');
  await u.click(within(form).getByRole('button', { name: 'Save project' }));
  await waitFor(() => expect(calls[0]).toMatchObject({ method: 'PATCH', path: '/v1/work/projects/prj_1', body: { name: 'House', ai_access: 'work' } }));
  await u.click(await screen.findByRole('button', { name: /Delete project/ }));
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Yes, delete the project' }));
  expect(await within(screen.getByRole('alertdialog')).findByRole('alert')).toHaveTextContent(/Only the person who made it/);
});

it('reloads the task list after a project and its tasks are deleted', async () => {
  const reads: Call[] = [];
  let gone = false;
  mount((c) => { if (c.method === 'DELETE' && c.path === '/v1/work/projects/prj_1') { gone = true; return new Response(null, { status: 204 }); } return undefined; }, () => (gone ? [] : [task]), reads);
  const u = userEvent.setup();
  expect(await screen.findByText('Pay rent')).toBeInTheDocument();
  await u.click(await screen.findByRole('button', { name: 'Delete project Home' }));
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Yes, delete the project' }));
  await waitFor(() => expect(screen.queryByText('Pay rent')).not.toBeInTheDocument());
  expect(reads.filter((r) => r.path === '/v1/work/tasks').length).toBeGreaterThan(1);
});
