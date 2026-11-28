// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

// P-08. Addresses are RFC 5737 documentation ranges.
const base = {
  available: true, reason: null, message: null, at: '2026-11-25T12:00:00Z', dropped: 0,
  interfaces: [
    { name: 'eth0', kind: 'ethernet', state: 'up', mac: '00:00:5e:00:53:01', mtu: 1500, addresses: ['192.0.2.10/24'], wifi: null },
    { name: 'wlan0', kind: 'wifi', state: 'down', mac: null, mtu: 1500, addresses: [], wifi: null },
  ],
  gateways: [{ interface: 'eth0', via: '192.0.2.1', family: 'ipv4' }], dns: ['192.0.2.53'], ports: [],
};
const idle = { can_change: true, reason: null, pending: null, last: null };
const json = (v: unknown, code = 200) => new Response(JSON.stringify(v), { status: code, headers: { 'content-type': 'application/json' } });

type Call = { method: string; path: string; body: Record<string, unknown> | null };

function mount(changes: unknown | (() => unknown), answer: (c: Call) => Response | undefined = () => undefined) {
  const calls: Call[] = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const call: Call = { method: init?.method ?? 'GET', path: new URL(String(url)).pathname, body: init?.body ? JSON.parse(String(init.body)) : null };
    calls.push(call);
    if (call.method === 'GET' && call.path === '/v1/network') return json({ ...base, changes: typeof changes === 'function' ? (changes as () => unknown)() : changes });
    return answer(call) ?? json({ error: 'not_found', message: 'unexpected call' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/network']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it('asks for a fixed address, files a request and points to the approval; nothing else is sent', async () => {
  const calls = mount(idle, (c) => (c.method === 'PUT' ? json({ id: 'act-5', type: 'network.configure', state: 'awaiting_approval' }, 202) : undefined));
  const user = userEvent.setup();
  expect(await screen.findByRole('form', { name: 'Change a cable connection' })).toBeInTheDocument();
  const options = screen.getAllByRole('option').map((o) => o.textContent);
  expect(options.some((o) => o?.startsWith('eth0 (192.0.2.10/24)'))).toBe(true);
  expect(options.some((o) => o?.startsWith('wlan0'))).toBe(false); // cables only
  await user.type(screen.getByLabelText('IP address with prefix'), '192.0.2.50/24');
  await user.type(screen.getByLabelText('Router (gateway)'), '192.0.2.1');
  await user.type(screen.getByLabelText(/DNS servers/), '192.0.2.53, 192.0.2.54');
  await user.selectOptions(screen.getByLabelText('Time to confirm'), '60');
  await user.click(screen.getByRole('button', { name: 'Ask to change' }));
  expect(await screen.findByRole('link', { name: 'Open request in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act-5');
  expect(screen.getByText(/open the box at 192\.0\.2\.50 and press Confirm on this page within 60 seconds/)).toBeInTheDocument();
  const put = calls.filter((c) => c.method !== 'GET');
  expect(put).toHaveLength(1);
  expect(put[0]).toMatchObject({ method: 'PUT', path: '/v1/network/eth0' });
  expect(put[0]?.body).toMatchObject({ mode: 'static', address: '192.0.2.50/24', gateway: '192.0.2.1', dns: ['192.0.2.53', '192.0.2.54'], rollback_seconds: 60 });
  expect(typeof put[0]?.body?.idempotency_key).toBe('string');
});

it('going back to DHCP sends no address, gateway or DNS', async () => {
  const calls = mount(idle, (c) => (c.method === 'PUT' ? json({ id: 'act-6', type: 'network.configure', state: 'awaiting_approval' }, 202) : undefined));
  const user = userEvent.setup();
  await user.click(await screen.findByRole('radio', { name: /Automatic \(DHCP\)/ }));
  expect(screen.queryByLabelText('IP address with prefix')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Ask to change' }));
  expect(await screen.findByText(/the address your router gives it/)).toBeInTheDocument();
  const body = calls.find((c) => c.method === 'PUT')?.body ?? {};
  expect(body).toMatchObject({ mode: 'dhcp', rollback_seconds: 120 });
  expect(body).not.toHaveProperty('address');
  expect(body).not.toHaveProperty('gateway');
  expect(body).not.toHaveProperty('dns');
});

it('shows the gateway\'s refusal word for word and files nothing', async () => {
  mount(idle, (c) => (c.method === 'PUT' ? json({ error: 'conflict', reason: 'invalid_gateway', message: 'The gateway must be another host inside 192.0.2.0/24.' }, 422) : undefined));
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('IP address with prefix'), '192.0.2.50/24');
  await user.type(screen.getByLabelText('Router (gateway)'), '198.51.100.1');
  await user.click(screen.getByRole('button', { name: 'Ask to change' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('The gateway must be another host inside 192.0.2.0/24.');
  expect(screen.queryByRole('link', { name: 'Open request in Approvals' })).not.toBeInTheDocument();
});

it('a change waiting for confirmation shows a countdown and a Confirm button instead of the form', async () => {
  const deadline = new Date(Date.now() + 90_000).toISOString();
  const pending = { action_id: 'act-7', interface: 'eth0', mode: 'static', address: '192.0.2.50/24', gateway: '192.0.2.1', dns: [], result: 'pending', started_at: new Date().toISOString(), deadline, ended_at: null };
  const calls = mount({ ...idle, pending }, (c) => (c.method === 'POST' && c.path === '/v1/network/eth0/confirm' ? json({ confirmed: true, interface: 'eth0' }) : undefined));
  const user = userEvent.setup();
  expect(await screen.findByText(/eth0 now has the fixed address 192\.0\.2\.50\/24/)).toBeInTheDocument();
  expect(screen.getByText(/goes back to its old settings in/)).toBeInTheDocument();
  expect(screen.getByText(/Open the box at 192\.0\.2\.50/)).toBeInTheDocument();
  expect(screen.queryByRole('form', { name: 'Change a cable connection' })).not.toBeInTheDocument();
  const button = screen.getByRole('button', { name: 'Confirm eth0' });
  expect(button).toBeDisabled();
  await user.click(button);
  expect(calls.some((c) => c.method === 'POST')).toBe(false);
  await user.click(screen.getByRole('checkbox', { name: /verified the Network page at the new IPv4 address/ }));
  await user.click(button);
  await waitFor(() => expect(calls).toContainEqual({
    method: 'POST', path: '/v1/network/eth0/confirm', body: { action_id: 'act-7', verified_reachable: true },
  }));
});

it('a late confirm says why it failed', async () => {
  const pending = { action_id: 'act-8', interface: 'eth0', mode: 'dhcp', address: null, gateway: null, dns: [], result: 'pending', started_at: new Date().toISOString(), deadline: new Date(Date.now() + 60_000).toISOString(), ended_at: null };
  mount({ ...idle, pending }, (c) => (c.method === 'POST' ? json({ error: 'conflict', reason: 'no_pending_change', message: 'no change to eth0 is waiting for confirmation (it may have rolled back already)' }, 409) : undefined));
  const user = userEvent.setup();
  await user.click(await screen.findByRole('checkbox', { name: /verified the Network page/ }));
  await user.click(screen.getByRole('button', { name: 'Confirm eth0' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('it may have rolled back already');
});

it('says when the last change rolled back by itself', async () => {
  const last = { interface: 'eth0', mode: 'static', address: '192.0.2.50/24', gateway: '192.0.2.1', dns: [], result: 'rolled_back', started_at: '2026-11-25T12:00:00Z', deadline: '2026-11-25T12:02:00Z', ended_at: '2026-11-25T12:02:00Z' };
  mount({ ...idle, last });
  expect(await screen.findByText(/was not confirmed in time, so the box went back to its old settings/)).toBeInTheDocument();
});

it('explains why it cannot change the network, with no form', async () => {
  mount({ can_change: false, reason: 'NetworkManager is not running on this box', pending: null, last: null });
  expect(await screen.findByText('NetworkManager is not running on this box')).toBeInTheDocument();
  expect(screen.queryByRole('form', { name: 'Change a cable connection' })).not.toBeInTheDocument();
});

it('shows nothing to change against a gateway that does not report changes', async () => {
  mount(undefined);
  expect(await screen.findByRole('heading', { level: 1, name: 'Network' })).toBeInTheDocument();
  expect(screen.queryByRole('form', { name: 'Change a cable connection' })).not.toBeInTheDocument();
});

it('a countdown that runs out is a rollback, never a confirmation', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const started = new Date().toISOString();
  const deadline = new Date(Date.now() + 5_000).toISOString();
  const pending = { action_id: 'act-9', interface: 'eth0', mode: 'static', address: '192.0.2.50/24', gateway: '192.0.2.1', dns: [], result: 'pending', started_at: started, deadline, ended_at: null };
  const last = { ...pending, result: 'rolled_back', ended_at: deadline };
  let rolledBack = false;
  const calls = mount(() => (rolledBack ? { ...idle, last } : { ...idle, pending }));
  const button = await screen.findByRole('button', { name: 'Confirm eth0' });
  fireEvent.click(screen.getByRole('checkbox', { name: /verified the Network page/ }));
  expect(button).toBeEnabled();
  rolledBack = true; // the box puts the old settings back by itself once the time is up
  await act(async () => { await vi.advanceTimersByTimeAsync(5_000 + 4_000 + 1_000); });
  expect(await screen.findByText(/was not confirmed in time, so the box went back to its old settings/)).toBeInTheDocument();
  expect(screen.queryByText(/Confirmed\. The change stays/)).not.toBeInTheDocument();
  expect(calls.some((c) => c.method === 'POST')).toBe(false);
});
