// SPDX-License-Identifier: Apache-2.0
import { act, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { seriousViolations } from '../test/helpers';

const live = {
  at: '2026-11-20T10:00:00Z',
  nodes: [
    { node_id: 'n1', hostname: 'beelink', status: 'online', stale: false, last_seen: '2026-11-20T10:00:00Z', age_s: 3, cpu_pct: 42, load1: 0.7,
      mem_used_mb: 2048, mem_total_mb: 8192, disk_used_gb: 40, disk_total_gb: 100, temp_c: 55, cpu_source: 'heartbeat' },
    { node_id: 'n2', hostname: 'pi5', status: 'stale', stale: true, last_seen: '2026-11-20T09:59:15Z', age_s: 45, cpu_pct: null,
      mem_used_mb: 1024, mem_total_mb: 4096, disk_used_gb: null, disk_total_gb: null, temp_c: null, cpu_source: 'heartbeat' },
  ],
  apps: { source: 'kubernetes', sampled_at: new Date().toISOString(), stale: false, items: [
    { app_id: 'kuma', name: 'Uptime Kuma', cpu_millicores: 300, mem_mb: 130, disk_mb: 3000 },
    { app_id: 'whoami', name: 'Whoami', cpu_millicores: 5, mem_mb: null, disk_mb: null },
  ] },
};
function response(value: unknown, code = 200) { return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } }); }

function mount(route: (path: string) => Response, mock = false) {
  const fetch = vi.fn(async (url: string | URL | Request) => route(new URL(String(url)).pathname));
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  const utils = render(<MemoryRouter initialEntries={['/usage']}><SessionProvider deps={{ mock, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={mock} /></SessionProvider></MemoryRouter>);
  return { fetch, ...utils };
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it('shows machines and apps from GET /v1/usage, with a dash for what nobody reported', async () => {
  const { fetch, container } = mount((p) => response(p === '/v1/usage' ? live : {}));
  const win = await screen.findByRole('region', { name: 'Live usage' });
  expect(await within(win).findByText('beelink')).toBeInTheDocument();
  expect(within(win).getByRole('meter', { name: 'Processor' })).toHaveAttribute('aria-valuenow', '42');
  expect(within(win).getByText('2.0 GB of 8.0 GB used')).toBeInTheDocument();
  expect(within(win).getByText(/Temperature: 55 °C/)).toBeInTheDocument();
  const row = within(win).getByRole('row', { name: /Uptime Kuma/ });
  expect(row).toHaveTextContent('300 m');
  expect(row).toHaveTextContent('130 MB');
  expect(row).toHaveTextContent('2.9 GB');
  expect(within(win).getByRole('row', { name: /Whoami/ })).toHaveTextContent('5 m––');
  expect(fetch.mock.calls.map(([u]) => new URL(String(u)).pathname)).toContain('/v1/usage');
  expect(await seriousViolations(container)).toEqual([]);
});

it('says a machine and the app runtime are stale instead of showing them as current', async () => {
  const stale = { ...live, apps: { ...live.apps, stale: true, sampled_at: new Date(Date.now() - 90_000).toISOString() } };
  mount((p) => response(p === '/v1/usage' ? stale : {}));
  const win = await screen.findByRole('region', { name: 'Live usage' });
  expect(await within(win).findByText(/last report from 45s ago, not live/)).toBeInTheDocument();
  expect(within(win).getByText(/Processor: this machine does not report it/)).toBeInTheDocument();
  expect(within(win).getByText(/runtime has not answered since 1m ago/)).toBeInTheDocument();
});

it('refreshes every 5 seconds and keeps the last reading, marked as old, when the hub stops answering', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  let fail = false;
  const { fetch } = mount((p) => (p !== '/v1/usage' ? response({}) : fail ? response({ error: 'x', message: 'down' }, 500) : response(live)));
  const win = await screen.findByRole('region', { name: 'Live usage' });
  await within(win).findByText('beelink');
  const polls = () => fetch.mock.calls.filter(([u]) => new URL(String(u)).pathname === '/v1/usage').length;
  const before = polls();
  await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
  expect(polls()).toBeGreaterThan(before);
  fail = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
  expect(await within(win).findByText(/Could not refresh: the hub did not answer. Showing the reading from/)).toBeInTheDocument();
  expect(within(win).getByText('beelink')).toBeInTheDocument();
});

it('says plainly when the box has no app runtime to read', async () => {
  mount((p) => response(p === '/v1/usage' ? { ...live, apps: { source: 'unavailable', sampled_at: null, stale: true, items: [] } } : {}));
  expect(await screen.findByText(/no app runtime the hub can read/)).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

it('opens from the menu bar', async () => {
  mount((p) => response(p === '/v1/usage' ? live : {}));
  const bar = await screen.findByRole('banner');
  expect(within(bar).getByRole('link', { name: 'Live usage' })).toHaveAttribute('href', '/usage');
});

it('has no usage data in demo mode and says so', async () => {
  const { fetch } = mount(() => response({}), true);
  expect(await screen.findByText(/Demo mode has no usage data/)).toBeInTheDocument();
  expect(fetch.mock.calls.some(([u]) => new URL(String(u)).pathname === '/v1/usage')).toBe(false);
});
