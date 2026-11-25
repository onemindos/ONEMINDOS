// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const summary = { node_id: 'storage-node', enabled: true, available: true, state: 'healthy', encrypted: true, used_bytes: 42, at: '2026-11-14T12:00:00Z', members: [], reasons: [] };
const care = {
  available: true,
  trim: { enabled: true, timer_state: 'active', last_run_at: '2026-11-23T00:07:14Z', last_result: 'success', last_trimmed_bytes: 13314398208, next_run_at: '2026-11-30T00:00:00Z' },
  smart: { daemon_state: 'active', alerts: [{ id: 'a1', at: '2026-11-25T01:00:00Z', device: '/dev/sda', kind: 'FailedHealthCheck', message: 'SMART health check failed' }] },
  removable: [
    { device: '/dev/sdb', name: 'sdb', model: 'Cruzer', label: 'HOLIDAY', size_bytes: 16e9, mountpoints: [], partitions: 1, ejectable: true },
    { device: '/dev/sdc', name: 'sdc', size_bytes: 5e11, mountpoints: ['/data/odd'], partitions: 1, ejectable: false, why_not: 'the box is using this drive (/data/odd)' },
  ],
};
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }); }
function mount(housekeeping: () => Response) {
  const posts: string[] = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    if (init?.method === 'POST') { posts.push(path); return response({ id: 'act-9', type: 'storage.eject', state: 'awaiting_approval' }, 202); }
    if (path === '/v1/storage/housekeeping') return housekeeping();
    return response(path === '/v1/storage' ? summary : []);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/storage']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return posts;
}
afterEach(() => vi.unstubAllGlobals());

it('shows the last and next TRIM, the smartd warning and the drives from the hub', async () => {
  mount(() => response(care));
  expect(await screen.findByText('Weekly TRIM')).toBeInTheDocument();
  expect(screen.getByText('12.4 GiB')).toBeInTheDocument();
  expect(screen.getByText(/SMART health check failed/)).toBeInTheDocument();
  expect(screen.getByText(/The disk watcher \(smartd\) is running/)).toBeInTheDocument();
  expect(screen.getByText('HOLIDAY')).toBeInTheDocument();
  expect(screen.getByText(/In use: the box is using this drive \(\/data\/odd\)/)).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: 'Safely remove' })).toHaveLength(1); // not offered for the drive in use
});

it('says plainly that TRIM has not run yet instead of inventing a date', async () => {
  mount(() => response({ ...care, trim: { ...care.trim, last_run_at: null, last_trimmed_bytes: null }, smart: { daemon_state: 'inactive', alerts: [] }, removable: [] }));
  expect(await screen.findByText('Has not run on this box yet')).toBeInTheDocument();
  expect(screen.getByText('No warnings from the disk watcher.')).toBeInTheDocument();
  expect(screen.getByText(/not running \(inactive\)/)).toBeInTheDocument();
  expect(screen.getByText('No USB drive is plugged in.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Safely remove' })).not.toBeInTheDocument();
});

it('files a request on Safely remove and points to the approval; it never approves', async () => {
  const posts = mount(() => response(care));
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Safely remove' }));
  expect(await screen.findByText(/Waiting for an owner to approve/)).toBeInTheDocument();
  expect(posts).toEqual(['/v1/storage/removable/sdb/eject']);
  expect(screen.getByRole('link', { name: 'Open the approval' })).toHaveAttribute('href', '/approvals?highlight=act-9');
  expect(screen.queryByRole('button', { name: 'Safely remove' })).not.toBeInTheDocument();
});

it('tells the owner when the host cannot be read and offers no remove button', async () => {
  mount(() => response({ available: false, message: 'The host service cannot be reached, so TRIM, disk warnings and drives cannot be read.' }));
  expect(await screen.findByText(/host service cannot be reached/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Safely remove' })).not.toBeInTheDocument();
});

it('refuses a malformed answer instead of showing it as healthy', async () => {
  mount(() => response({ available: true, trim: 'fine' }));
  await waitFor(() => expect(screen.getByText(/invalid TRIM status/)).toBeInTheDocument());
  expect(screen.queryByText('Weekly TRIM')).not.toBeInTheDocument();
});
