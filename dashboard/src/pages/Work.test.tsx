// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const task = (id: string, title: string, extra: Record<string, unknown> = {}) => ({
  id, project_id: 'prj_1', revision: 3, title, body: '', status: 'todo', priority: 4, labels: [], assignee: null,
  due_at: null, section_id: null, repeat: null, dependencies: [], updated_at: '2026-11-25T15:00:00Z', ...extra,
});
const json = (value: unknown, code = 200) => new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } });

function mount(route: (method: string, path: string, query: string, body: unknown, headers: Headers) => Response) {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = new URL(String(url));
    return route(init?.method ?? 'GET', u.pathname, u.search, init?.body ? JSON.parse(String(init.body)) : undefined, new Headers(init?.headers));
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/work']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('shows Today first, switches to Upcoming and Inbox, and says so when a view is empty', async () => {
  const asked: string[] = [];
  mount((_method, path, query) => {
    if (path === '/v1/work/tasks') {
      const view = new URLSearchParams(query).get('view') ?? '';
      asked.push(`?view=${view}`);
      expect(new URLSearchParams(query).get('tz')).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
      return json(view === 'today' ? [task('tsk_1', 'Pay rent', { priority: 1, labels: ['bills'], due_at: '2026-11-25T22:00:00Z' })] : []);
    }
    return json({});
  });
  const user = userEvent.setup();
  expect(await screen.findByText('Pay rent')).toBeInTheDocument();
  expect(screen.getByText(/p1/)).toBeInTheDocument();
  expect(screen.getByText(/@bills/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Upcoming' }));
  expect(await screen.findByText('Nothing coming up.')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Inbox' }));
  expect(await screen.findByText('Your Inbox is empty.')).toBeInTheDocument();
  expect(asked).toEqual(expect.arrayContaining(['?view=today', '?view=upcoming', '?view=inbox']));
});

it('quick-adds one line with an idempotency key and the browser time zone', async () => {
  const sent: { body: unknown; key: string | null }[] = [];
  mount((method, path, _q, body, headers) => {
    if (method === 'POST' && path === '/v1/work/quick-add') { sent.push({ body, key: headers.get('Idempotency-Key') }); return json(task('tsk_2', 'Fix tap'), 201); }
    return json([]);
  });
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Quick add'), 'Fix tap tomorrow #Home');
  await user.click(screen.getByRole('button', { name: 'Add' }));
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]!.body).toEqual({ text: 'Fix tap tomorrow #Home', tz: Intl.DateTimeFormat().resolvedOptions().timeZone });
  expect(sent[0]!.key).toMatch(/\S{8,}/);
});

it('completes a task with the revision it was read at, and reports a conflict', async () => {
  const calls: { ifMatch: string | null; body: unknown }[] = [];
  mount((method, path, _q, body, headers) => {
    if (method === 'PATCH') { calls.push({ ifMatch: headers.get('If-Match'), body }); return json({ error: 'stale_precondition', message: 'changed' }, 409); }
    return json(path === '/v1/work/tasks' ? [task('tsk_1', 'Pay rent')] : {});
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Done' }));
  await waitFor(() => expect(calls).toEqual([{ ifMatch: '3', body: { status: 'done' } }]));
  expect(await screen.findByText(/changed meanwhile/)).toBeInTheDocument();
});

it('shows the zone a repeating task counts in and changes it with the rule and revision it was read at', async () => {
  const repeating = task('tsk_3', 'Standup', { revision: 5, repeat: { every: 'weekday', interval: 1, tz: 'America/New_York' } });
  const calls: { ifMatch: string | null; body: unknown }[] = [];
  mount((method, path, _q, body, headers) => {
    if (method === 'PATCH') { calls.push({ ifMatch: headers.get('If-Match'), body }); return json({ ...repeating, revision: 6 }); }
    return json(path === '/v1/work/tasks' ? [repeating] : {});
  });
  const user = userEvent.setup();
  expect(await screen.findByText(/repeats every weekday/)).toBeInTheDocument();
  expect(screen.getByText(/\(America\/New_York\)/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Change repeat time zone of Standup' }));
  const box = screen.getByLabelText('Repeat time zone');
  await user.clear(box);
  await user.type(box, 'Europe/Paris');
  await user.click(screen.getByRole('button', { name: 'Save zone' }));
  await waitFor(() => expect(calls).toEqual([{ ifMatch: '5', body: { repeat: { every: 'weekday', interval: 1, tz: 'Europe/Paris' } } }]));
});

it('says so when the gateway does not know the time zone', async () => {
  const repeating = task('tsk_3', 'Standup', { repeat: { every: 'day', interval: 2, tz: null } });
  mount((method, path) => {
    if (method === 'PATCH') return json({ error: 'conflict', message: 'bad' }, 422);
    return json(path === '/v1/work/tasks' ? [repeating] : {});
  });
  const user = userEvent.setup();
  expect(await screen.findByText(/\(UTC\)/)).toBeInTheDocument();
  await user.click(await screen.findByRole('button', { name: 'Change repeat time zone of Standup' }));
  const box = screen.getByLabelText('Repeat time zone');
  await user.clear(box);
  await user.type(box, 'Mars/Base');
  await user.click(screen.getByRole('button', { name: 'Save zone' }));
  expect(await screen.findByText(/time zone is not known/)).toBeInTheDocument();
});

it('previews the quick-add line without creating a task', async () => {
  const sent: Array<{ path: string; body: unknown }> = [];
  mount((method, path, _query, body) => {
    if (method === 'POST') {
      sent.push({ path, body });
      return json({ title: 'Fix tap', project: 'Home', project_found: true, priority: 2, labels: ['water'] });
    }
    return json([]);
  });
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Quick add'), 'Fix tap #Home p2 @water');
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  expect(await screen.findByText('Fix tap · Home · p2 · @water')).toBeVisible();
  expect(sent).toEqual([{ path: '/v1/work/parse', body: { text: 'Fix tap #Home p2 @water', tz: Intl.DateTimeFormat().resolvedOptions().timeZone } }]);
});

it('loads comments and activity, then posts and removes the signed-in person’s comment', async () => {
  const path = '/v1/work/projects/prj_1/tasks/tsk_1';
  const author = DEMO_TOKENS['owner-demo']!.id;
  let comments: Array<{ id: string; author_id: string; body: string }> = [];
  const writes: string[] = [];
  mount((method, url, _query, body, headers) => {
    if (url === '/v1/work/tasks') return json([task('tsk_1', 'Pay rent')]);
    if (url === `${path}/activity`) return json([{ id: 1, actor_id: author, kind: 'created', fields: [], at: '2026-11-25T15:00:00Z' }]);
    if (url === `${path}/comments` && method === 'GET') return json(comments);
    if (url === `${path}/comments` && method === 'POST') {
      expect(headers.get('Idempotency-Key')).toMatch(/\S{8,}/);
      expect(body).toEqual({ body: 'Paid in full' });
      const row = { id: 'cmt_1', author_id: author, body: 'Paid in full' };
      comments.push(row);
      writes.push('posted');
      return json(row, 201);
    }
    if (url === `${path}/comments/cmt_1` && method === 'DELETE') {
      comments = [];
      writes.push('deleted');
      return new Response(null, { status: 204 });
    }
    return json([]);
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Discussion and activity for Pay rent' }));
  expect(await screen.findByRole('list', { name: 'Task activity' })).toHaveTextContent('created');
  await user.type(screen.getByLabelText('Comment'), 'Paid in full');
  await user.click(screen.getByRole('button', { name: 'Post comment' }));
  await user.click(await screen.findByRole('button', { name: 'Delete comment: Paid in full' }));
  expect(await screen.findByText('No comments yet.')).toBeVisible();
  expect(writes).toEqual(['posted', 'deleted']);
});

it('manages project members and sections and captures a task in the selected section', async () => {
  const path = '/v1/work/projects/prj_1';
  const writes: Array<{ method: string; path: string; body: unknown }> = [];
  let members: string[] = ['person-a'];
  let sections: Array<{ id: string; name: string }> = [];
  mount((method, url, _query, body, headers) => {
    if (url === '/v1/work/projects') return json([{ id: 'prj_1', name: 'Home', ai_access: 'none' }]);
    if (method === 'GET' && url === path) return json({ id: 'prj_1', name: 'Home', ai_access: 'none' });
    if (method === 'GET' && url === `${path}/members`) return json(members);
    if (method === 'GET' && url === `${path}/sections`) return json(sections);
    if (method === 'GET') return json([]);
    writes.push({ method, path: url, body });
    if (method === 'PUT') { members.push('person-b'); return new Response(null, { status: 204 }); }
    if (method === 'POST' && url.endsWith('/sections')) {
      expect(headers.get('Idempotency-Key')).toMatch(/\S{8,}/);
      sections = [{ id: 'sec_1', name: 'Later' }];
      return json(sections[0], 201);
    }
    if (method === 'PATCH') { sections = [{ id: 'sec_1', name: 'Next week' }]; return json(sections[0]); }
    if (method === 'DELETE') {
      if (url.endsWith('person-b')) members = ['person-a']; else sections = [];
      return new Response(null, { status: 204 });
    }
    expect(headers.get('Idempotency-Key')).toMatch(/\S{8,}/);
    return json(task('tsk_2', 'Fix tap'), 201);
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Details for Home' }));
  const details = within(await screen.findByRole('region', { name: 'Project details for Home' }));
  expect(details.getByRole('list', { name: 'Project members' })).toHaveTextContent('person-a');
  await user.type(details.getByLabelText('Person ID'), 'person-b');
  await user.click(details.getByRole('button', { name: 'Add person' }));
  await user.click(await details.findByRole('button', { name: 'Remove person-b from the project' }));
  await waitFor(() => expect(details.queryByText('person-b')).not.toBeInTheDocument());
  await user.type(details.getByLabelText('New section'), 'Later');
  await user.click(details.getByRole('button', { name: 'Add section' }));
  await user.click(await details.findByRole('button', { name: 'Rename section Later' }));
  await user.clear(details.getByLabelText('Section name'));
  await user.type(details.getByLabelText('Section name'), 'Next week');
  await user.click(details.getByRole('button', { name: 'Save section' }));
  await details.findByRole('button', { name: 'Rename section Next week' });
  await user.type(details.getByLabelText('Title'), 'Fix tap');
  await user.selectOptions(details.getByLabelText('Section'), 'sec_1');
  await user.click(details.getByRole('button', { name: 'Create task' }));
  await waitFor(() => expect(details.getByLabelText('Title')).toHaveValue(''));
  await user.click(details.getByRole('button', { name: 'Delete section Next week' }));
  await waitFor(() => expect(details.queryByRole('button', { name: 'Delete section Next week' })).not.toBeInTheDocument());
  expect(writes).toEqual([
    { method: 'PUT', path: `${path}/members/person-b`, body: undefined },
    { method: 'DELETE', path: `${path}/members/person-b`, body: undefined },
    { method: 'POST', path: `${path}/sections`, body: { name: 'Later' } },
    { method: 'PATCH', path: `${path}/sections/sec_1`, body: { name: 'Next week' } },
    { method: 'POST', path: '/v1/work/capture', body: { title: 'Fix tap', project_id: 'prj_1', section_id: 'sec_1' } },
    { method: 'DELETE', path: `${path}/sections/sec_1`, body: undefined },
  ]);
});
