// SPDX-License-Identifier: Apache-2.0
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { openScreen } from '../test/helpers';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const summary = { node_id: 'storage-node', enabled: true, available: true, state: 'healthy', encrypted: true, used_bytes: 42, at: '2026-11-14T12:00:00Z', members: [{ devid: 1, missing: false, size_bytes: 100, allocated_bytes: 55, errors: {} }], reasons: [] };
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }); }
function mount(override?: (path: string) => Response | Promise<Response>) {
  const fetch = vi.fn(async (url: string | URL | Request) => {
    const path = new URL(String(url)).pathname;
    if (override) return override(path);
    return response(path === '/v1/storage' ? summary : [{ id: 'disk-1', path: '/dev/testdisk', model: 'Test disk', serial_tail: '1234', size_bytes: 100, role: 'member', health: { verdict: 'warning', temperature_c: 63, reasons: ['temperature above warning limit'] } }]);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/storage']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('reaches real storage and SMART data without computing fictional free capacity', async () => {
  const fetch = mount();
  expect(await screen.findByRole('heading', { level: 1, name: 'Storage' })).toBeInTheDocument();
  expect(await screen.findByText('Test disk')).toBeInTheDocument();
  expect(screen.getByText('42 bytes')).toBeInTheDocument();
  expect(screen.getByText('63 °C')).toBeInTheDocument();
  expect(screen.getByText('temperature above warning limit')).toBeInTheDocument();
  expect(screen.queryByText(/45 bytes free/)).not.toBeInTheDocument();
  // The page reads storage; the Offline maps card beside it reads the map packs and sites (OfflineMaps.test.tsx).
  expect(fetch.mock.calls.every(([url]) => /^\/v1\/(storage|map\/packs|sites)/.test(new URL(String(url)).pathname))).toBe(true);
  await openScreen(userEvent.setup(), 'Activity');
  expect(screen.queryByRole('article', { name: 'Storage and disk health' })).not.toBeInTheDocument();
});

it('shows disabled storage honestly without offering disk-changing controls', async () => {
  mount((path) => path === '/v1/storage' ? response({ node_id: 'node', enabled: false, available: false }) : response({ error: 'stale_precondition', message: 'storage is disabled' }, 409));
  expect(await screen.findByText('Storage is disabled on this hub.')).toBeInTheDocument();
  expect(screen.queryByText(/^healthy$/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /format|wipe|claim|remove/i })).not.toBeInTheDocument();
});

it('does not lose general health when the gateway denies owner-only device identities', async () => {
  mount((path) => path === '/v1/storage' ? response(summary) : response({ error: 'permission_denied', message: 'only an owner may do this' }, 403));
  expect(await screen.findByText('42 bytes')).toBeInTheDocument();
  expect(await screen.findByText(/Your account is not allowed to see this/)).toBeInTheDocument();
  expect(screen.queryByText('/dev/testdisk')).not.toBeInTheDocument();
});

it('preserves last data on refresh failure and labels it stale', async () => {
  let reads = 0;
  mount((path) => path === '/v1/storage' ? ++reads === 1 ? response(summary) : response({ error: 'unavailable', message: 'node down' }, 503) : response([]));
  expect(await screen.findByText('42 bytes')).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Refresh storage' }));
  await waitFor(() => expect(screen.getByText(/previously fetched storage data/)).toBeInTheDocument());
  expect(screen.getByText('42 bytes')).toBeInTheDocument();
});

it('handles malformed status without crashing the page or claiming health', async () => {
  mount((path) => response(path === '/v1/storage' ? {} : []));
  expect(await screen.findByText(/invalid storage status/)).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1, name: 'Storage' })).toBeInTheDocument();
  expect(within(screen.getByRole('main')).queryByText(/^healthy$/)).not.toBeInTheDocument();
});

it('does not let an older success erase a newer refresh failure', async () => {
  let reads = 0;
  let finishOlder!: (value: Response) => void;
  const older = new Promise<Response>((resolve) => { finishOlder = resolve; });
  mount((path) => {
    if (path !== '/v1/storage') return response([]);
    reads++;
    return reads === 1 ? response(summary) : reads === 2 ? older : response({ error: 'unavailable', message: 'newer failure' }, 503);
  });
  expect(await screen.findByText('42 bytes')).toBeInTheDocument();
  const u = userEvent.setup();
  await u.click(screen.getByRole('button', { name: 'Refresh storage' }));
  await u.click(screen.getByRole('button', { name: 'Refresh storage' }));
  expect(await screen.findByText(/previously fetched storage data/)).toBeInTheDocument();
  await act(async () => { finishOlder(response({ ...summary, used_bytes: 99 })); });
  expect(screen.getByText(/previously fetched storage data/)).toBeInTheDocument();
  expect(screen.getByText('42 bytes')).toBeInTheDocument();
  expect(screen.queryByText('99 bytes')).not.toBeInTheDocument();
});
