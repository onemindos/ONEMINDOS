// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
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
