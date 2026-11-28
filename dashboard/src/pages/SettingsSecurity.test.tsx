// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { SettingsActivityMonitor, SettingsPermissions, SettingsSecurity } from './SettingsSecurity';

const state = vi.hoisted(() => ({ role: 'owner', signOut: vi.fn() }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture' }), useSession: () => ({ signOut: state.signOut }) }));
vi.mock('../shell/Shell', () => ({ useShell: () => ({ role: state.role }) }));
afterEach(() => vi.unstubAllGlobals());

function gateway(responses: Record<string, unknown>) {
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    expect(init.method).toBe('GET');
    const response = responses[new URL(url).pathname];
    if (response === 403) return Response.json({ error: 'permission_denied', message: 'Denied' }, { status: 403 });
    return response === undefined ? Response.json({}, { status: 404 }) : Response.json(response);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

it('shows an actual verified audit and distinguishes a refusal from an unknown status', async () => {
  state.role = 'owner';
  gateway({ '/v1/auth/passkeys': [{ id: 'key', level: 'L2' }, { id: 'phone', level: 'L1' }], '/v1/audit/verify': { ok: true }, '/v1/physical/lockout': 403,
    '/v1/verification-requirements': { household_level: 'L1', grace: true, recovery_needed: false } });
  render(<MemoryRouter><SettingsSecurity /></MemoryRouter>);
  expect(await screen.findByText('2 registered · 1 proven')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Sign-in keys' })).toHaveAttribute('href', '/settings/sign-in-keys');
  expect(screen.getByRole('link', { name: 'Verification levels' })).toHaveAttribute('href', '/settings/verification');
  expect(screen.getByText('Before your first proven key: confirmed at the box')).toBeVisible();
  expect(screen.getByText('Verified')).toBeVisible();
  expect(screen.getByText('Owner only')).toBeVisible();
  expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0);
});

it('keeps box-wide security rows and reads out of adult sessions', async () => {
  state.role = 'adult';
  const fetch = gateway({ '/v1/auth/passkeys': [{ id: 'key' }], '/v1/auth/methods': { password: true, totp: false, passkeys: 1, passkeys_active: true } });
  render(<MemoryRouter><SettingsSecurity /></MemoryRouter>);
  expect(await screen.findByText('1 registered · 0 proven')).toBeVisible();
  expect(await screen.findByText('Off (a fallback; passkeys come first)')).toBeVisible();
  expect(screen.queryByText('Audit chain')).toBeNull();
  expect(fetch.mock.calls.every(([url]) => ['/v1/auth/passkeys', '/v1/auth/sessions', '/v1/tokens', '/v1/auth/methods'].includes(new URL(url).pathname))).toBe(true);
});

it('shows app roles and the people returned by the access endpoint', async () => {
  state.role = 'owner';
  gateway({
    '/v1/users': 403,
    '/v1/apps': [{ id: 'notes', name: 'Notes' }],
    '/v1/apps/notes/access': { roles: ['adult'], people: [{ display_name: 'Test person' }] },
  });
  render(<SettingsPermissions />);
  expect(await screen.findByText('Owner only')).toBeVisible();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'By app' }));
  await user.selectOptions(await screen.findByLabelText('App'), 'notes');
  expect(await screen.findByText('Roles: adult. People: Test person.')).toBeVisible();
  // An owner gets the sharing editor right there (#1214); it only reads until Save.
  expect(await screen.findByRole('heading', { name: 'Who can open Notes' })).toBeVisible();
});

it('offers no sharing editor to a non-owner', async () => {
  state.role = 'adult';
  gateway({ '/v1/users': 403, '/v1/apps': [{ id: 'notes', name: 'Notes' }], '/v1/apps/notes/access': { roles: ['adult'], people: [] } });
  render(<SettingsPermissions />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'By app' }));
  await user.selectOptions(await screen.findByLabelText('App'), 'notes');
  expect(await screen.findByText('Roles: adult. People: None.')).toBeVisible();
  expect(screen.queryByRole('heading', { name: 'Who can open Notes' })).toBeNull();
});

it('labels stale counters and links to Usage and Activity without sending a write', async () => {
  gateway({
    '/v1/usage': { apps: { stale: true, items: [{ app_id: 'notes', name: 'Notes', cpu_millicores: 2 }] } },
    '/v1/system/services': { services: [] },
    '/v1/agents': [], '/v1/actions': [], '/v1/auth/sessions': [],
  });
  render(<MemoryRouter><SettingsActivityMonitor /></MemoryRouter>);
  expect(await screen.findByText('Notes · Stale')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Usage history' })).toHaveAttribute('href', '/usage');
  expect(screen.getByRole('link', { name: 'Audit activity' })).toHaveAttribute('href', '/activity');
});
