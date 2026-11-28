// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'content-type': 'application/json' } });
const pack = { id: 'eu-west', region: 'Western Europe', bytes: 412_000_000, sha256: 'a'.repeat(64), installed_at: '2026-11-01T10:00:00Z' };
const site = { id: 'home', name: 'Family house', floors: [{ id: 'f1', name: 'Ground' }], areas: [{ id: 'a1', name: 'Kitchen' }, { id: 'a2', name: 'Garage' }], anchors: [] };

function mount(handler: (path: string, method: string) => Response | undefined = () => undefined, token = 'owner-demo') {
  const calls: { method: string; path: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : {} });
    const custom = handler(path, method);
    if (custom) return custom;
    if (path === '/v1/storage') return json({ node_id: 'n', enabled: false, available: false });
    if (path === '/v1/storage/devices') return json([]);
    if (path === '/v1/map/packs') return json({ packs: [pack], free_bytes: 20_500_000_000 });
    if (path === '/v1/sites') return json([site]);
    if (path === '/v1/instance') return json({ name: 'Box', version: '0.1.0', hub_node_id: 'n' });
    if (path === '/v1/actions' && method === 'POST') return json({ id: 'act-9', type: 'map.pack.remove', state: 'awaiting_approval' }, 201);
    return json({ error: 'not_found', message: path }, 404);
  }));
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/storage']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); });

it('shows the installed map packs, the free map disk and the map sites', async () => {
  mount();
  const card = within(await screen.findByRole('article', { name: 'Offline maps' }));
  expect(await card.findByText(/20.5 GB free for map packs/)).toBeInTheDocument();
  expect(card.getByText('Western Europe')).toBeInTheDocument();
  expect(card.getByText(/412 MB/)).toBeInTheDocument();
  expect(card.getByText('Family house')).toBeInTheDocument();
  expect(card.getByText(/1 floors · 2 areas/)).toBeInTheDocument();
});

it('files a removal request only after a confirmation, and says the pack stays until approved', async () => {
  const calls = mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Ask to take away the Western Europe pack' }));
  expect(calls.some((c) => c.method === 'POST')).toBe(false);
  await u.click(screen.getByRole('button', { name: 'File the request' }));
  expect(await screen.findByText(/Request act-9 was filed/)).toBeInTheDocument();
  const post = calls.find((c) => c.method === 'POST' && c.path === '/v1/actions')!;
  expect(post.body).toMatchObject({ type: 'map.pack.remove', params: { pack_id: 'eu-west' }, idempotency_key: expect.any(String) });
  expect(screen.getByRole('link', { name: 'Review it in Approvals' })).toHaveAttribute('href', '/approvals');
  expect(screen.getByText('Western Europe')).toBeInTheDocument(); // not removed by asking
});

it('says Offline Maps is not set up, instead of inventing free space', async () => {
  mount((path) => (path === '/v1/map/packs' ? json({ packs: [], free_bytes: null }) : path === '/v1/sites' ? json([]) : undefined));
  expect(await screen.findByText(/Offline Maps is not set up on this box/)).toBeInTheDocument();
  expect(screen.getByText('No map packs are installed.')).toBeInTheDocument();
  expect(screen.getByText(/No map sites are set up/)).toBeInTheDocument();
});

it('does not show the card to an account that may not read maps', async () => {
  mount((path) => (path === '/v1/map/packs' || path === '/v1/sites' ? json({ error: 'permission_denied', message: 'no' }, 403) : undefined), 'child-demo');
  await screen.findByRole('heading', { level: 1, name: 'Storage' });
  expect(screen.queryByRole('article', { name: 'Offline maps' })).not.toBeInTheDocument();
});
