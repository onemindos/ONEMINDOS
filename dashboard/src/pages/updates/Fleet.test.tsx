// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';

function mount(token: string) {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/updates']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const fleet = { machines: [{ node_id: 'n1', hostname: 'hub', board: 'x86_64-efi', status: 'online', version: '1.2.0', update_state: 'idle', available_version: '1.3.0', updatable: true }], versions: [{ version: '1.2.0', count: 1 }], active_rollout_id: null };
const paused = { id: 'rol_aaaaaaaaaaaaaaaaaaaaaaaaaa', version: '1.3.0', state: 'paused', stage: 0, stages: [10, 100], reason: 'a machine rolled back', counts: { waiting: 1, offered: 0, succeeded: 0, failed: 1 }, nodes: [] };
function gateway(rollouts: unknown[], calls: { path: string; method: string; body?: Record<string, unknown> }[]) {
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    if (method !== 'GET') calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path === '/v1/os/fleet') return json(fleet);
    if (path === '/v1/os/rollouts') return json(rollouts);
    if (path === '/v1/actions' && method === 'POST') { const b = JSON.parse(String(init!.body)); return json({ id: 'act_7', type: b.type, params: b.params, state: 'awaiting_approval' }, 201); }
    if (path.endsWith('/cancel')) return json({ ...paused, state: 'cancelled' });
    if (path === '/v1/os/updates') return json({ nodes: [], install: { available: false } });
    if (path === '/v1/os/updates/history') return json({ events: [], requests: [] });
    return json({ error: 'not_found', message: path }, 404);
  }));
}
afterEach(() => vi.unstubAllGlobals());

it('shows every machine with its version and the rollouts with their wave and reason', async () => {
  gateway([paused], []);
  mount('owner-demo');
  const fleetCard = await screen.findByRole('region', { name: 'Fleet' });
  expect(await within(fleetCard).findByText('hub')).toBeInTheDocument();
  expect(within(fleetCard).getByText('1.2.0')).toBeInTheDocument();
  expect(await within(fleetCard).findByText(/Paused: needs a decision · wave 1 of 2/)).toBeInTheDocument();
  expect(within(fleetCard).getByText('a machine rolled back')).toBeInTheDocument();
  // The fleet's count is a number: it reads "1 machine", never "Not reported".
  expect(within(fleetCard).getByText('Versions in use: 1.2.0 on 1 machine.')).toBeInTheDocument();
});

it('only files a request to start a rollout: nothing is approved', async () => {
  const calls: { path: string; method: string; body?: Record<string, unknown> }[] = [];
  gateway([], calls);
  mount('owner-demo');
  const u = userEvent.setup();
  await u.type(await screen.findByLabelText('Version to roll out'), '1.3.0');
  await u.click(screen.getByRole('button', { name: 'Ask to start a rollout' }));
  expect(await screen.findByText(/Roll out 1.3.0: waiting for an owner/)).toBeInTheDocument();
  expect(calls).toHaveLength(1);
  expect(calls[0]!.body).toMatchObject({ type: 'os.rollout.start', params: { version: '1.3.0' }, idempotency_key: expect.any(String) });
  expect(calls.some((c) => c.path.includes('approve'))).toBe(false);
  expect(screen.getByRole('link', { name: 'Open it in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act_7');
});

it('asks before cancelling, then cancels once', async () => {
  const calls: { path: string; method: string; body?: Record<string, unknown> }[] = [];
  gateway([paused], calls);
  mount('owner-demo');
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Cancel rollout' }));
  expect(calls).toHaveLength(0);
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Yes, cancel the rollout' }));
  await vi.waitFor(() => expect(calls).toEqual([{ path: '/v1/os/rollouts/rol_aaaaaaaaaaaaaaaaaaaaaaaaaa/cancel', method: 'POST', body: undefined }]));
});

it('offers no rollout controls to an adult', async () => {
  gateway([paused], []);
  mount('adult-demo');
  await screen.findByText(/Paused: needs a decision/);
  expect(screen.queryByRole('button', { name: 'Cancel rollout' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Ask to resume' })).not.toBeInTheDocument();
});
