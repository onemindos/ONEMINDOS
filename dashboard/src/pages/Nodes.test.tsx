// SPDX-License-Identifier: Apache-2.0
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { SessionProvider } from '../session';

const params = { node_id: 'gpu', target_sha256: 'a'.repeat(64) };
function mount(available = true, ambiguous = false, failedCapability = false, invalidFingerprint = false, rejection?: string) {
  let writes = 0;
  let nodeReadFails = false;
  const ledger: Record<string, unknown>[] = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url), window.location.origin).pathname;
    if (path === '/v1/instance') return Response.json({ name: 'Test hub', version: '1', hub_node_id: 'hub' });
    if (path === '/v1/nodes' && nodeReadFails) throw new TypeError('hub disconnected');
    if (path === '/v1/nodes') return Response.json([{
      node_id: 'gpu', hostname: 'GPU box', role: 'node', board: 'x86_64-efi', arch: 'amd64', os: { pretty: 'Debian' },
      cpus: 4, mem_total_mb: 8192, mem_available_mb: 4096, disk_total_gb: 100, disk_free_gb: 50,
      k3s: { present: false, ready: false }, rauc: { present: false, booted_slot: null },
      status: 'offline', last_seen: new Date(Date.now() - 300_000).toISOString(),
    }]);
    if (path === '/v1/nodes/gpu/wake') return failedCapability
      ? Response.json({ error: 'unavailable', message: 'read failed' }, { status: 503 })
      : Response.json({ available, reason: available ? 'Owner approval required' : 'No valid configured wake target', params: available ? { ...params, ...(invalidFingerprint ? { target_sha256: 'not-a-fingerprint' } : {}) } : null });
    if (path === '/v1/actions' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body));
      writes++;
      if (rejection && writes === 1) return Response.json({ error: rejection, message: 'Gateway refused outdated request' }, { status: 409 });
      if (ambiguous && writes === 1) return Response.json({});
      const action = { ...body, id: 'wake-action', state: 'awaiting_approval' };
      ledger.push(action);
      return Response.json(action, { status: 201 });
    }
    if (path === '/v1/actions') return Response.json(ledger);
    if (path === '/v1/apps') return Response.json([]);
    return Response.json({ error: 'not_found', message: 'not configured in fixture' }, { status: 404 });
  });
  vi.stubGlobal('fetch', fetch);
  const token = `test-wake-${available}-${ambiguous}-${failedCapability}-${rejection ?? ''}`;
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/nodes']}><SessionProvider deps={{ mock: false, makeApi: () => new HttpApi({ token }), knownPrincipal: () => ({ id: token, kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { fetch, disconnect: () => { nodeReadFails = true; }, user: userEvent.setup(), posts: () => fetch.mock.calls.filter(([, init]) => init?.method === 'POST') };
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it('confirms a known-node request without approving or claiming awake', async () => {
  const { user, posts } = mount();
  await user.click(await screen.findByRole('button', { name: 'Request wake' }));
  expect(posts()).toHaveLength(0);
  const dialog = screen.getByRole('alertdialog');
  expect(dialog).toHaveTextContent(/Nothing runs until the owner approves/);
  await user.click(within(dialog).getByRole('button', { name: 'Send request' }));
  expect(await screen.findByRole('link', { name: 'Review wake request' })).toHaveAttribute('href', '/approvals?highlight=wake-action');
  expect(posts()).toHaveLength(1);
  expect(JSON.parse(String(posts()[0]![1]?.body))).toMatchObject({ type: 'node.wake', params });
  expect(screen.getByRole('article', { name: 'GPU box' })).toHaveTextContent('Offline');
  expect(screen.queryByText('Awake')).not.toBeInTheDocument();
  await user.click(screen.getByRole('link', { name: 'Review wake request' }));
  expect(await screen.findByRole('button', { name: 'Approve Wake up gpu' })).toBeEnabled();
  expect(screen.getAllByText('Wake up gpu').length).toBeGreaterThan(0);
  expect(posts()).toHaveLength(1); // Navigating to approval never approves automatically.
});

it('retains the exact request after an incomplete reply', async () => {
  const { user, posts } = mount(true, true);
  await user.click(await screen.findByRole('button', { name: 'Request wake' }));
  await user.click(screen.getByRole('button', { name: 'Send request' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/may already have been filed/);
  await user.click(screen.getByRole('button', { name: 'Retry same request' }));
  await screen.findByRole('link', { name: 'Review wake request' });
  expect(posts()).toHaveLength(2);
  expect(posts()[0]![1]?.body).toBe(posts()[1]![1]?.body);
});

it.each(['expired', 'stale_precondition'])('allows an explicit new request only after a conclusive %s rejection', async (rejection) => {
  const { user, posts } = mount(true, false, false, false, rejection);
  await user.click(await screen.findByRole('button', { name: 'Request wake' }));
  await user.click(screen.getByRole('button', { name: 'Send request' }));
  await screen.findByRole('alert');
  await user.click(screen.getByRole('button', { name: 'Send request' }));
  await screen.findByRole('link', { name: 'Review wake request' });
  expect(JSON.parse(String(posts()[0]![1]?.body)).idempotency_key).not.toBe(JSON.parse(String(posts()[1]![1]?.body)).idempotency_key);
});

it('disables malformed capability data instead of offering a request', async () => {
  const { posts } = mount(true, false, false, true);
  await screen.findByText('Owner approval required');
  expect(screen.getByRole('button', { name: 'Request wake' })).toBeDisabled();
  expect(posts()).toHaveLength(0);
});

it('keeps the last offline card but disables requests after a failed node refresh', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  const { disconnect, posts } = mount();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Request wake' })).toBeEnabled());
  disconnect();
  await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
  expect(screen.getByRole('article', { name: 'GPU box' })).toHaveTextContent('Offline');
  expect(screen.getByRole('button', { name: 'Request wake' })).toBeDisabled();
  expect(posts()).toHaveLength(0);
});

it.each([false, true])('fails closed for unavailable or unreadable capability (read failure=%s)', async (failed) => {
  const { posts } = mount(false, false, failed);
  await screen.findByText(failed ? /Wake availability could not be refreshed/ : /No valid configured wake target/);
  expect(screen.getByRole('button', { name: 'Request wake' })).toBeDisabled();
  expect(posts()).toHaveLength(0);
});
