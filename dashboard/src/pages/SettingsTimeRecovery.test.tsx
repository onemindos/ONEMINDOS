// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { SettingsDateTime, SettingsRecoveryReset } from './SettingsTimeRecovery';

const state = vi.hoisted(() => ({ role: 'owner', signOut: vi.fn() }));
vi.mock('../shell/Shell', () => ({ useShell: () => ({ role: state.role }) }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture' }), useSession: () => ({ signOut: state.signOut }) }));

afterEach(() => vi.unstubAllGlobals());

function gateway(offset: number, options: { time?: object | number; action?: string } = {}) {
  const saved = { box_name: 'hill-hub', time_zone: 'UTC', backup_choice: 'later', backup_destination_id: null, saved: true };
  const live = { available: true, zone: 'UTC', ntp_enabled: true, ntp_synchronized: true, server: '0.debian.pool.ntp.org', stratum: 2,
    last_sync_at: '2026-11-25T12:00:00Z', at: '2026-11-25T12:30:00Z' };
  let actionState = 'awaiting_approval';
  const request = vi.fn(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === '/v1/instance') return Response.json({}, { headers: { Date: new Date(Date.now() + offset).toUTCString() } });
    if (path === '/v1/onboarding/settings') return Response.json(saved);
    if (path === '/v1/system/time' && typeof options.time === 'number') return Response.json({ error: 'permission_denied', message: 'Owner only' }, { status: options.time });
    if (path === '/v1/system/time') return Response.json(options.time ?? live);
    if (path === '/v1/system/time/zone' && init.method === 'POST') return Response.json({ id: 'act-1', state: 'awaiting_approval', type: 'system.set_timezone' }, { status: 202 });
    if (path === '/v1/actions/act-1') { actionState = options.action ?? 'succeeded'; return Response.json({ id: 'act-1', state: actionState }); }
    if (path === '/v1/backups/status') return Response.json({ last_verified_restore_at: null });
    if (path === '/v1/backups/kit') return Response.json({ error: 'permission_denied', message: 'Owner only' }, { status: 403 });
    if (path === '/v1/system/controls') return Response.json({
      controls: [{ type: 'system.factory_reset', label: 'Factory reset', needs_passkey: true, available: true }], pending: [],
    });
    throw new Error(`Unexpected test route ${path}`);
  });
  vi.stubGlobal('fetch', request);
  return request;
}

it('warns at three minutes, shows the live sync state, and the owner requests a time zone change', async () => {
  state.role = 'owner';
  const network = gateway(180_000);
  render(<MemoryRouter><SettingsDateTime /></MemoryRouter>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Sign-in codes may fail');
  expect(await screen.findByText('Synchronised with a time server')).toBeVisible();
  expect(screen.getByText('0.debian.pool.ntp.org (stratum 2)')).toBeVisible();
  const field = await screen.findByLabelText('Time zone');
  const user = userEvent.setup();
  await user.clear(field);
  await user.type(field, 'America/New_York');
  await user.click(screen.getByRole('button', { name: 'Request time zone change' }));
  expect(await screen.findByText('Waiting for an owner to approve it in Approvals.')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Open Approvals' })).toHaveAttribute('href', '/approvals');
  const submitted = network.mock.calls.find((call) => call[1].method === 'POST');
  expect(JSON.parse(String(submitted?.[1].body))).toEqual({ zone: 'America/New_York' });
  // Nothing else is written: the request waits for approval, and onboarding settings are untouched.
  expect(network.mock.calls.filter((call) => call[1].method === 'PUT')).toHaveLength(0);
});

it('stops following the request once its outcome is unknown, and says so', async () => {
  state.role = 'owner';
  const network = gateway(0, { action: 'outcome_unknown' });
  render(<MemoryRouter><SettingsDateTime /></MemoryRouter>);
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Time zone'), '/x');
  await user.click(screen.getByRole('button', { name: 'Request time zone change' }));
  expect(await screen.findByText(/could not confirm whether the change was applied/, {}, { timeout: 6000 })).toBeVisible();
  const polls = () => network.mock.calls.filter((call) => new URL(String(call[0])).pathname === '/v1/actions/act-1').length;
  const seen = polls();
  await new Promise((resolve) => setTimeout(resolve, 3500));
  expect(polls()).toBe(seen); // no further poll after a final state
}, 15000);

it('says so when the clock is not synchronised, and when the hub cannot report it', async () => {
  state.role = 'owner';
  gateway(0, { time: { available: true, zone: 'Europe/Berlin', ntp_enabled: true, ntp_synchronized: false, server: null } });
  const first = render(<SettingsDateTime />);
  expect(await screen.findByText('Not synchronised yet: no time server reached')).toBeVisible();
  expect(screen.getByText('Europe/Berlin')).toBeVisible();
  first.unmount();
  gateway(0, { time: { available: false, reason: 'host_service_unreachable', message: 'the host service is not reachable' } });
  render(<SettingsDateTime />);
  expect(await screen.findByText('the host service is not reachable')).toBeVisible();
  expect(screen.queryByLabelText('Time zone')).toBeNull(); // no form while the host cannot apply it
});

it('shows no warning at thirty seconds, and offers no time-zone write to a nonowner', async () => {
  state.role = 'adult';
  gateway(30_000, { time: 403 });
  render(<SettingsDateTime />);
  expect(await screen.findByText('UTC')).toBeVisible();
  expect(await screen.findByText('Owner only')).toBeVisible();
  expect(screen.queryByLabelText('Time zone')).toBeNull();
  expect(screen.queryByRole('alert')).toBeNull();
});

it('links to the existing passkey-gated request flow and never writes a reset', async () => {
  const network = gateway(0);
  render(<MemoryRouter><SettingsRecoveryReset /></MemoryRouter>);
  expect(await screen.findByText('Owner only')).toBeVisible();
  expect(await screen.findByText('Factory reset · Available to request')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Open system controls' })).toHaveAttribute('href', '/troubleshoot');
  expect(network.mock.calls.every((call) => call[1].method === 'GET')).toBe(true);
});
