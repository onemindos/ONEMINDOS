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

function gateway(offset: number) {
  const saved = { box_name: 'hill-hub', time_zone: 'UTC', backup_choice: 'later', backup_destination_id: null, saved: true };
  const request = vi.fn(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === '/v1/instance') return Response.json({}, { headers: { Date: new Date(Date.now() + offset).toUTCString() } });
    if (path === '/v1/onboarding/settings') return Response.json(init.method === 'PUT' ? { ...saved, ...JSON.parse(String(init.body)) } : saved);
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

it('warns at three minutes and the owner saves a time zone without changing backup settings', async () => {
  state.role = 'owner';
  const network = gateway(180_000);
  render(<SettingsDateTime />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Sign-in codes may fail');
  const field = await screen.findByLabelText('Time zone');
  const user = userEvent.setup();
  await user.clear(field);
  await user.type(field, 'America/New_York');
  await user.click(screen.getByRole('button', { name: 'Save time zone' }));
  expect(await screen.findByText('Time zone saved.')).toBeVisible();
  const submitted = network.mock.calls.find((call) => call[1].method === 'PUT');
  expect(JSON.parse(String(submitted?.[1].body))).toEqual({
    box_name: 'hill-hub', time_zone: 'America/New_York', backup_choice: 'later', backup_destination_id: null,
  });
});

it('shows no warning at thirty seconds, and offers no time-zone write to a nonowner', async () => {
  state.role = 'adult';
  gateway(30_000);
  render(<SettingsDateTime />);
  expect(await screen.findByText('UTC')).toBeVisible();
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

it('shows the disk key line and adds the typed kit key to destinations added after the kit (design 25a)', async () => {
  state.role = 'owner';
  let missing = ['dst_new'];
  const request = vi.fn(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === '/v1/backups/status') return Response.json({ last_verified_restore_at: null });
    if (path === '/v1/backups/kit') return Response.json({ state: 'confirmed', missing_on: missing, disk_key: 'included' });
    if (path === '/v1/backups/kit/attach') { missing = []; return Response.json({ action: { id: 'act_1', state: 'succeeded' } }); }
    if (path === '/v1/system/controls') return Response.json({ controls: [], pending: [] });
    throw new Error(`Unexpected test route ${path} ${init.method}`);
  });
  vi.stubGlobal('fetch', request);
  render(<MemoryRouter><SettingsRecoveryReset /></MemoryRouter>);
  expect(await screen.findByText('In the kit')).toBeVisible();
  const field = await screen.findByLabelText('Owner recovery key and check group');
  const user = userEvent.setup();
  const button = screen.getByRole('button', { name: 'Add the key to the new destinations' });
  expect(button).toBeDisabled();
  await user.type(field, 'ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567-ABCD-EFGH-IJKL-MNOP-QRST WXYZ');
  await user.click(button);
  const sent = request.mock.calls.find((call) => new URL(call[0]).pathname === '/v1/backups/kit/attach');
  expect(JSON.parse(String(sent?.[1].body))).toMatchObject({ check: 'WXYZ' });
  expect(JSON.parse(String(sent?.[1].body)).groups).toHaveLength(13);
  expect(await screen.findByText('In the kit')).toBeVisible();
  await vi.waitFor(() => expect(screen.queryByLabelText('Owner recovery key and check group')).toBeNull());
});
