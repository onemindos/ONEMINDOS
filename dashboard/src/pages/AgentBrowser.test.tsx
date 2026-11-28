// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

function mount(token: string) {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/settings/agents']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
const json = (body: unknown, code = 200) => new Response(JSON.stringify(body), { status: code, headers: { 'content-type': 'application/json' } });
function gateway(sites: unknown[] = [{ id: 'site1', agent: 'ops-agent', entry: '*.example.org', plan_sha256: 'x', action_id: 'a1', approved_by: 'owner', created_at: '2026-11-26T12:00:00Z' }]) {
  const sessions: unknown[] = [{ id: 'sess1', agent: 'ops-agent', state: 'running', pages: 2, max_pages: 20, pages_left: 18, created_at: '2026-11-26T12:00:00Z', expires_at: '2026-11-26T13:00:00Z', ended_reason: null }];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    if (path === '/v1/agents/kill-switch') return json({ on: false, changed_by: null, changed_at: null, reason: null });
    if (path === '/v1/agent-browser/sites' && method === 'GET') return json(sites);
    if (path === '/v1/agent-browser/sites' && method === 'POST') return json({ id: 'act-77', state: 'awaiting_approval' }, 201);
    if (path === '/v1/agent-browser/sites/site1' && method === 'DELETE') { sites.length = 0; return json({ removed: true, id: 'site1' }); }
    if (path === '/v1/agent-browser/sessions' && method === 'GET') return json(sessions);
    if (path === '/v1/agent-browser/sessions/sess1' && method === 'DELETE') { sessions.length = 0; return json({ id: 'sess1', state: 'ended' }); }
    return json({ error: 'not_found', message: path }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
const calls = (fetch: ReturnType<typeof gateway>, method: string) => fetch.mock.calls.filter(([, i]) => i?.method === method);
afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); });

it('lists approved sites and sessions, and takes a site away only after a confirmation', async () => {
  const fetch = gateway();
  mount('owner-demo');
  const card = await screen.findByRole('article', { name: 'Agent browser' });
  expect(await within(card).findByText('*.example.org')).toBeInTheDocument();
  expect(await within(card).findByText(/2 of 20 pages used/)).toBeInTheDocument();
  const u = userEvent.setup();
  await u.click(within(card).getByRole('button', { name: 'Take away *.example.org from ops-agent' }));
  expect(calls(fetch, 'DELETE')).toHaveLength(0);
  await u.click(screen.getByRole('button', { name: 'Take it away' }));
  await waitFor(() => expect(calls(fetch, 'DELETE')).toHaveLength(1));
  expect(String(calls(fetch, 'DELETE')[0]![0])).toContain('/v1/agent-browser/sites/site1');
});

it('files a request for a site instead of allowing it, and points to Approvals', async () => {
  const fetch = gateway([]);
  mount('owner-demo');
  const card = await screen.findByRole('article', { name: 'Agent browser' });
  expect(await within(card).findByText(/No site is approved/)).toBeInTheDocument();
  const u = userEvent.setup();
  await u.type(within(card).getByLabelText(/^Site/), 'docs.example.org');
  await u.type(within(card).getByLabelText('Agent it is for'), 'ops-agent');
  await u.click(within(card).getByRole('button', { name: 'Ask to allow this site' }));
  expect(await within(card).findByText(/Request act-77 was filed/)).toBeInTheDocument();
  const [url, init] = calls(fetch, 'POST')[0]!;
  expect(String(url)).toContain('/v1/agent-browser/sites');
  expect(JSON.parse(String(init!.body))).toEqual({ entry: 'docs.example.org', agent: 'ops-agent' });
  expect(new Headers(init!.headers).get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
  expect(within(card).getByRole('link', { name: 'Review it in Approvals' })).toHaveAttribute('href', '/approvals');
  expect(within(card).getByText(/No site is approved/)).toBeInTheDocument(); // nothing is allowed until approved
});

it('ends a session at once', async () => {
  const fetch = gateway();
  mount('owner-demo');
  const card = await screen.findByRole('article', { name: 'Agent browser' });
  await userEvent.setup().click(await within(card).findByRole('button', { name: 'End the session of ops-agent' }));
  await waitFor(() => expect(calls(fetch, 'DELETE')).toHaveLength(1));
  expect(String(calls(fetch, 'DELETE')[0]![0])).toContain('/v1/agent-browser/sessions/sess1');
});
it('retries a failed site request with the same key, so Approvals gets it once', async () => {
  let n = 0;
  const fetch = gateway([]);
  const base = fetch.getMockImplementation()!;
  fetch.mockImplementation(async (url, init) => {
    if (new URL(String(url)).pathname === '/v1/agent-browser/sites' && init?.method === 'POST' && ++n === 1) return json({ error: 'bad', message: 'try again' }, 400);
    return base(url, init);
  });
  mount('owner-demo');
  const card = await screen.findByRole('article', { name: 'Agent browser' });
  const u = userEvent.setup();
  await u.type(await within(card).findByLabelText(/^Site/), 'docs.example.org');
  await u.type(within(card).getByLabelText('Agent it is for'), 'ops-agent');
  await u.click(within(card).getByRole('button', { name: 'Ask to allow this site' }));
  await waitFor(() => expect(calls(fetch, 'POST')).toHaveLength(1));
  await u.click(within(card).getByRole('button', { name: 'Ask to allow this site' }));
  expect(await within(card).findByText(/Request act-77 was filed/)).toBeInTheDocument();
  const keys = calls(fetch, 'POST').map(([, i]) => new Headers(i!.headers).get('Idempotency-Key'));
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});
it.each(['adult-demo', 'child-demo', 'guest-demo'])('does not show the card or read the agent browser as %s', async (token) => {
  const fetch = gateway();
  mount(token);
  expect((await screen.findAllByRole('heading', { level: 1 })).length).toBeGreaterThan(0); // the settings page rendered
  await new Promise((r) => setTimeout(r, 50));
  expect(screen.queryByRole('article', { name: 'Agent browser' })).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([u]) => String(u).includes('/v1/agent-browser/'))).toBe(false);
});
