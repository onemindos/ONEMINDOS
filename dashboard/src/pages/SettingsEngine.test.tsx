// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { seriousViolations } from '../test/helpers';
import { SettingsEngine } from './SettingsEngine';

// The shape of GET /v1/engine (core/onemind_core/engine/feed.py) for the owner.
const owner = {
  at: '2026-11-22T10:00:00Z',
  scope: 'all',
  monitor: { state: 'up', checked_at: '2026-11-22T10:00:00Z', errors: {} },
  health: { status: 'ok', error: null },
  links: { up: 1, down: 1 },
  jetstream: { state: 'ready', reason: '', enabled: true, used_bytes: 67108864, cap_bytes: 268435456, planned_cap_bytes: 268435456, used_pct: 25, reserved_bytes: 1, streams: 3, consumers: 2 },
  server: { version: '2.15.3', uptime: '1h', connections: 4, total_connections: 9, leafnodes: 1, in_msgs: 1, out_msgs: 2 },
  accounts: [
    { account: 'ONEMIND', node_id: null, connections: 2, leafnodes: 0, jetstream_bytes: 67108864 },
    { account: 'NODE_aaaa1111', node_id: 'aaaa1111', connections: 1, leafnodes: 1, jetstream_bytes: null },
  ],
  nodes: [
    { node_id: 'aaaa1111', link: 'up', rtt: '1.2ms', heartbeat: 'online', outbox: { stream: 'NODE_node_aaaa1111_OUTBOX', messages: 47, bytes: 4700, lag: 40, last_active_s: 1.5, error: null } },
    { node_id: 'bbbb2222', link: 'down', rtt: null, heartbeat: 'stale', outbox: null },
  ],
  slow_consumers: { total: 1, clients: 1, routes: 0, gateways: 0, leafs: 0 },
  connections_truncated: false,
};
const summary = { ...owner, scope: 'summary', accounts: [], nodes: [], server: null, slow_consumers: null };

function response(value: unknown, code = 200) {
  return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } });
}

function mount(route: (path: string) => Response, mock = false) {
  const fetch = vi.fn(async (url: string | URL | Request) => route(new URL(String(url)).pathname));
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  const utils = render(
    <MemoryRouter>
      <SessionProvider deps={{ mock, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}>
        <SettingsEngine />
      </SessionProvider>
    </MemoryRouter>,
  );
  return { fetch, ...utils };
}
afterEach(() => vi.unstubAllGlobals());

it('shows the bus, the links, the message store and each machine for the owner, from GET /v1/engine', async () => {
  const { fetch, container } = mount((p) => response(p === '/v1/engine' ? owner : {}));
  expect(await screen.findByText(/1 machine connected, 1 not connected/)).toBeInTheDocument();
  expect(screen.getByText('Running')).toBeInTheDocument();
  expect(screen.getByRole('meter', { name: 'Message store' })).toHaveAttribute('aria-valuenow', '67108864');
  expect(screen.getByText('64.0 MiB of 256.0 MiB used')).toBeInTheDocument();
  const a = screen.getByRole('row', { name: /^aaaa1111/ });
  expect(within(a).getByText('Connected')).toBeInTheDocument();
  expect(a).toHaveTextContent('40');
  expect(within(screen.getByRole('row', { name: /^bbbb2222/ })).getByText('Not connected')).toBeInTheDocument();
  expect(screen.getByRole('row', { name: /^NODE_aaaa1111/ })).toHaveTextContent('1');
  expect(fetch.mock.calls.map(([u]) => new URL(String(u)).pathname)).toContain('/v1/engine');
  expect(await seriousViolations(container)).toEqual([]);
});

it('shows a non-owner only the summary', async () => {
  mount((p) => response(p === '/v1/engine' ? summary : {}));
  expect(await screen.findByText(/1 machine connected/)).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(screen.queryByText('Technical details')).not.toBeInTheDocument();
});

it('says the message store is off when NATS has no cap, instead of showing a meter', async () => {
  const refused = { ...owner, jetstream: { ...owner.jetstream, state: 'refused', reason: 'NATS runs JetStream without a cap; the hub refuses that', cap_bytes: 0 } };
  mount((p) => response(p === '/v1/engine' ? refused : {}));
  expect(await screen.findByText(/switched off because it has no size limit/)).toBeInTheDocument();
  expect(screen.queryByRole('meter')).not.toBeInTheDocument();
});

it('says when the bus is not answering', async () => {
  const down = { ...summary, monitor: { state: 'down', checked_at: 't', errors: {} }, health: { status: 'unknown', error: null }, links: { up: 0, down: 0 } };
  mount((p) => response(p === '/v1/engine' ? down : {}));
  expect(await screen.findByText('Not answering')).toBeInTheDocument();
  expect(screen.getByText(/No other machine is joined yet/)).toBeInTheDocument();
});

it('is not shown to a person without monitoring:read', async () => {
  const { fetch } = mount((p) => (p === '/v1/engine' ? response({ error: 'permission_denied', message: 'no' }, 403) : response({})));
  await vi.waitFor(() => expect(fetch.mock.calls.some(([u]) => new URL(String(u)).pathname === '/v1/engine')).toBe(true));
  await vi.waitFor(() => expect(screen.queryByText('Engine')).not.toBeInTheDocument());
  expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
});

it('has no engine data in demo mode and says so', async () => {
  const { fetch } = mount(() => response({}), true);
  expect(await screen.findByText(/Demo mode has no engine data/)).toBeInTheDocument();
  expect(fetch.mock.calls.some(([u]) => new URL(String(u)).pathname === '/v1/engine')).toBe(false);
});
