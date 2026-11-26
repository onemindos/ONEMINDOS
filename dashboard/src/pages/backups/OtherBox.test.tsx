// SPDX-License-Identifier: Apache-2.0
import { configure, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';

configure({ asyncUtilTimeout: 8000 });
const KEY = 'k'.repeat(40);
const json = (body: unknown, code = 200) => new Response(JSON.stringify(body), { status: code, headers: { 'content-type': 'application/json' } });
type Call = { method: string; path: string; body: Record<string, unknown>; idem: string | null };

function mount(token = 'owner-demo', candidates: () => Response = () => json({ destination_id: 'dst_0123456789abcdef', points: [{ run_id: 'run1', taken_at: '2026-11-20T03:00:00Z', reason: null, system: true, apps: ['notes', 'kuma'], snapshot_ids: [] }] })) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const headers = new Headers(init?.headers);
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(String(init.body)) : {}, idem: headers.get('Idempotency-Key') });
    if (path === '/v1/backups/status') return json({ health: 'ok', reason: null, last_success_at: null, last_verified_restore_at: null, next_run_at: null, badges: { box: { state: 'backed_up' } } });
    if (path === '/v1/backups/destinations') return json([{ id: 'dst_0123456789abcdef', label: 'Garage disk', kind: 'usb' }]);
    if (path === '/v1/backups/runs' || path === '/v1/backups/snapshots' || path === '/v1/restores') return json([]);
    if (path === '/v1/onboarding/restore/candidates') return candidates();
    if (path === '/v1/onboarding/restore/apps') return json({ id: 'act_42', type: 'backup.restore', state: 'awaiting_approval', restore: null }, 202);
    return json({ error: 'not_found', message: path }, 404);
  }));
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/backups']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); });

it('lists restore points for the old box and files an unapproved restore, then forgets the key', async () => {
  const calls = mount();
  const u = userEvent.setup();
  const card = within(await screen.findByRole('region', { name: 'Restore an app from another box’s backup' }));
  const look = card.getByRole('button', { name: 'Look for restore points' });
  expect(look).toBeDisabled();
  await u.type(card.getByLabelText('Old box ID'), 'box-old');
  await u.type(card.getByLabelText('Recovery key (from the kit)'), 'short');
  expect(look).toBeDisabled(); // a key shorter than the kit's is refused before it is sent
  await u.clear(card.getByLabelText('Recovery key (from the kit)'));
  await u.type(card.getByLabelText('Recovery key (from the kit)'), KEY);
  expect(card.getByLabelText('Recovery key (from the kit)')).toHaveAttribute('type', 'password');
  await u.click(look);
  await u.click(await card.findByRole('button', { name: 'Restore notes from 2026-11-20T03:00:00Z' }));
  expect(await card.findByText(/Request act_42 to restore notes was filed and is not approved/)).toBeInTheDocument();
  expect(card.getByText(/if the box restarts before you approve, the request cannot run/)).toBeInTheDocument();
  expect(card.getByRole('link', { name: 'Review it in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act_42');
  const post = calls.find((c) => c.path === '/v1/onboarding/restore/apps')!;
  expect(post.body).toEqual({ destination_id: 'dst_0123456789abcdef', box_id: 'box-old', recovery_key: KEY, run_id: 'run1', app_id: 'notes', approve: false });
  expect(post.idem).toBeTruthy();
  expect(card.getByLabelText('Recovery key (from the kit)')).toHaveValue('');
  expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false);
});

it('says why when the backup cannot be read, and does not list anything', async () => {
  mount('owner-demo', () => json({ error: 'stale_precondition', message: 'the backup could not be read: wrong recovery key, wrong disk or no backup there' }, 409));
  const u = userEvent.setup();
  const card = within(await screen.findByRole('region', { name: 'Restore an app from another box’s backup' }));
  await u.type(card.getByLabelText('Old box ID'), 'box-old');
  await u.type(card.getByLabelText('Recovery key (from the kit)'), KEY);
  await u.click(card.getByRole('button', { name: 'Look for restore points' }));
  expect(await card.findByRole('alert')).toHaveTextContent('wrong recovery key');
  expect(card.queryByRole('list', { name: 'Restore points' })).not.toBeInTheDocument();
});

it('is not offered to anyone but the owner', async () => {
  mount('adult-demo');
  await screen.findByRole('heading', { level: 1, name: 'Backups' });
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Restore an app from another box’s backup' })).not.toBeInTheDocument());
});

it('retries a lost restore reply with the same key on the one shared client', async () => {
  let n = 0;
  const calls = mount();
  const base = (globalThis.fetch as ReturnType<typeof vi.fn>).getMockImplementation()!;
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(async (url: string | URL | Request, init?: RequestInit) => {
    if (new URL(String(url)).pathname === '/v1/onboarding/restore/apps' && ++n === 1) { calls.push({ method: 'POST', path: '/v1/onboarding/restore/apps', body: JSON.parse(String(init!.body)), idem: new Headers(init?.headers).get('Idempotency-Key') }); return json({ error: 'conflict', message: 'busy' }, 409); }
    return base(url, init);
  });
  const u = userEvent.setup();
  const card = within(await screen.findByRole('region', { name: 'Restore an app from another box’s backup' }));
  await u.type(card.getByLabelText('Old box ID'), 'box-old');
  await u.type(card.getByLabelText('Recovery key (from the kit)'), KEY);
  await u.click(card.getByRole('button', { name: 'Look for restore points' }));
  const btn = await card.findByRole('button', { name: 'Restore notes from 2026-11-20T03:00:00Z' });
  await u.click(btn);
  expect(await card.findByRole('alert')).toHaveTextContent('will not file a second request');
  await u.click(card.getByRole('button', { name: 'Restore notes from 2026-11-20T03:00:00Z' }));
  expect(await card.findByText(/Request act_42 to restore notes was filed/)).toBeInTheDocument();
  const keys = calls.filter((c) => c.path === '/v1/onboarding/restore/apps').map((c) => c.idem);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[0]).toBe(keys[1]);
});

it('skips a point without a run id, which holds no app to pick', async () => {
  mount('owner-demo', () => json({ destination_id: 'dst_0123456789abcdef', points: [{ run_id: null, taken_at: null, reason: 'manual', system: true, apps: ['x'], snapshot_ids: [] }] }));
  const u = userEvent.setup();
  const card = within(await screen.findByRole('region', { name: 'Restore an app from another box’s backup' }));
  await u.type(card.getByLabelText('Old box ID'), 'box-old');
  await u.type(card.getByLabelText('Recovery key (from the kit)'), KEY);
  await u.click(card.getByRole('button', { name: 'Look for restore points' }));
  expect(await card.findByText('That backup holds no restore points for this key.')).toBeInTheDocument();
});
