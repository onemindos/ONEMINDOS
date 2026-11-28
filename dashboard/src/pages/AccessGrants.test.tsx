// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { AccessGrants, allows } from './AccessGrants';

const state = vi.hoisted(() => ({ mock: false, canDecide: 'yes' }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture', mock: state.mock, canDecide: state.canDecide }), useSession: () => ({ signOut: vi.fn() }) }));
afterEach(() => { vi.unstubAllGlobals(); state.mock = false; state.canDecide = 'yes'; });

const grant = (id: string, over: Record<string, unknown> = {}) => ({
  id, data_class: 'location', grantee: { kind: 'app', id: 'owntracks' }, read: true, write: false, aggregate: true,
  created_at: '2026-11-01T00:00:00Z', expires_at: '2027-11-01T00:00:00Z', requested_by: 'app:owntracks', approved_by: 'zeus',
  action_id: 'act_1', revoked_at: null, revoked_by: null, active: true, ...over,
});
const hostGrant = { id: 'hg_1', app_id: 'zigbee2mqtt', kind: 'device', device_class: 'usb-serial', path: '/dev/ttyUSB0', reason: 'Zigbee stick',
  active: true, granted_at: '2026-11-02T00:00:00Z', approved_by: 'zeus', action_id: 'act_2', revoked_at: null, revoked_by: null };

// A gateway with the routes of core/onemind_core/routers/datagrants.py and host_grants.py.
function gateway(opts: { revokeStatus?: number; revokeDown?: boolean } = {}) {
  let data = [grant('dgr_1'), grant('dgr_old', { active: false, revoked_at: '2026-11-03T00:00:00Z' })];
  let host = [hostGrant];
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    const method = init?.method ?? 'GET';
    calls.push(`${method} ${path}`);
    if (method === 'GET' && path === '/v1/data/grants') return Response.json(data);
    if (method === 'GET' && path === '/v1/host-grants') return Response.json({ grants: host });
    if (opts.revokeDown) throw new TypeError('Failed to fetch');
    if (opts.revokeStatus) return Response.json({ error: 'not_found', message: 'no active host grant with this id' }, { status: opts.revokeStatus });
    if (method === 'DELETE' && path === '/v1/data/grants/dgr_1') { data = data.map((g) => (g.id === 'dgr_1' ? { ...g, active: false } : g)); return Response.json(data[0]); }
    if (method === 'POST' && path === '/v1/host-grants/hg_1/revoke') { host = []; return Response.json({ ...hostGrant, active: false }); }
    return Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  }));
  return calls;
}

it('says what a grant allows in words', () => {
  expect(allows({ read: true, write: false, aggregate: true })).toBe('read and count');
  expect(allows({ read: true, write: true, aggregate: true })).toBe('read, add records and count');
  expect(allows({ read: false, write: false, aggregate: false })).toBe('nothing');
});

it('shows the owner the live data and hardware grants, and counts the ended ones', async () => {
  gateway();
  render(<AccessGrants />);
  expect(await screen.findByText('App: owntracks')).toBeInTheDocument();
  expect(screen.getByText('Where people and things are')).toBeInTheDocument();
  expect(screen.getByText('read and count')).toBeInTheDocument();
  expect(screen.getByText('1 earlier grant has ended or been revoked.')).toBeInTheDocument();
  expect(await screen.findByText('zigbee2mqtt')).toBeInTheDocument();
  expect(screen.getByText('A device: usb-serial: /dev/ttyUSB0')).toBeInTheDocument();
});

it('revokes a data grant only after a second click', async () => {
  const calls = gateway();
  const user = userEvent.setup();
  render(<AccessGrants />);
  await user.click(await screen.findByRole('button', { name: 'Revoke access for owntracks (location)' }));
  expect(calls.some((c) => c.startsWith('DELETE'))).toBe(false);
  await user.click(within(screen.getByRole('group', { name: 'Revoke access for owntracks (location)?' })).getByRole('button', { name: 'Revoke' }));
  expect(await screen.findByText('Revoked: owntracks (location) has no access any more.')).toBeInTheDocument();
  expect(calls).toContain('DELETE /v1/data/grants/dgr_1');
  expect(await screen.findByText('Nobody has been given access to data beyond what everyone sees.')).toBeInTheDocument();
});

it('revokes hardware access for an app', async () => {
  const calls = gateway();
  const user = userEvent.setup();
  render(<AccessGrants />);
  await user.click(await screen.findByRole('button', { name: 'Revoke access for zigbee2mqtt' }));
  await user.click(within(screen.getByRole('group', { name: 'Revoke access for zigbee2mqtt?' })).getByRole('button', { name: 'Revoke' }));
  expect(await screen.findByText('No app has hardware access.')).toBeInTheDocument();
  expect(calls).toContain('POST /v1/host-grants/hg_1/revoke');
});

it('says a gone grant in plain words', async () => {
  gateway({ revokeStatus: 404 });
  const user = userEvent.setup();
  render(<AccessGrants />);
  await user.click(await screen.findByRole('button', { name: 'Revoke access for zigbee2mqtt' }));
  await user.click(within(screen.getByRole('group', { name: 'Revoke access for zigbee2mqtt?' })).getByRole('button', { name: 'Revoke' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('That grant is already gone.');
});

it('says nothing was revoked when the box does not answer', async () => {
  gateway({ revokeDown: true });
  const user = userEvent.setup();
  render(<AccessGrants />);
  await user.click(await screen.findByRole('button', { name: 'Revoke access for zigbee2mqtt' }));
  await user.click(within(screen.getByRole('group', { name: 'Revoke access for zigbee2mqtt?' })).getByRole('button', { name: 'Revoke' }));
  expect(await screen.findByRole('alert', {}, { timeout: 5000 })).toHaveTextContent('The box did not answer. Nothing was revoked; try again.');
});

it('shows someone who is not an owner their own grants, with no revoke and no hardware list', async () => {
  const calls = gateway();
  state.canDecide = 'no';
  render(<AccessGrants />);
  expect(await screen.findByText('App: owntracks')).toBeInTheDocument();
  expect(screen.getByText(/Only an owner can revoke a line/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Revoke/ })).toBeNull();
  expect(screen.queryByRole('heading', { name: 'Hardware access' })).toBeNull();
  expect(calls).not.toContain('GET /v1/host-grants');
});

it('calls nothing in demo mode', () => {
  state.mock = true;
  const calls = gateway();
  render(<AccessGrants />);
  expect(screen.getByText(/Demo mode lists none/)).toBeInTheDocument();
  expect(calls).toEqual([]);
});
