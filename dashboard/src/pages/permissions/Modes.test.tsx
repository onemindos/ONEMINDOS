// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { toRoute } from '../../shell/routes';
import { PermissionsPage } from './PermissionsPage';

const session = vi.hoisted(() => ({
  token: 'old-session',
  signIn: vi.fn(async () => undefined),
  logout: vi.fn(async () => undefined),
  loginOptions: vi.fn(async () => ({ publicKey: { challenge: 'abc' } })),
  loginPasskey: vi.fn(async () => ({ access_token: 'fresh-session' })),
}));
vi.mock('../../session', () => ({
  useSession: () => ({ signOut: vi.fn() }),
  useSignedIn: () => ({ token: session.token, signIn: session.signIn, api: { logout: session.logout },
    anon: { loginOptions: session.loginOptions, loginPasskey: session.loginPasskey } }),
}));
vi.mock('../../shell/Shell', () => ({ useShell: () => ({ role: 'owner' }) }));
vi.mock('../../lib/webauthn', () => ({ webauthnSupported: () => true, getPasskey: vi.fn(async () => ({ id: 'cred' })) }));

type Call = { method: string; path: string; body?: unknown; auth: string | null };
let calls: Call[] = [];
let modes: Array<Record<string, unknown>> = [];

const mode = (principal: string, m: string, own = true, passkey = true) =>
  ({ principal, mode: m, own, household_default: 'ask', owner_passkey: passkey, set_by: null, set_at: null, reason: null });

function gateway(put: (c: Call) => Response) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    const call = { method: init.method ?? 'GET', path, body: init.body ? JSON.parse(String(init.body)) : undefined,
      auth: new Headers(init.headers).get('Authorization') };
    calls.push(call);
    if (call.method === 'PUT') return put(call);
    if (path === '/v1/permission-modes') return Response.json(modes);
    if (path === '/v1/agents') return Response.json([{ id: 'notes-helper', budget_per_day: 50, used_24h: 0, pending_approvals: 0, cancelled: false }]);
    if (path === '/v1/users') return Response.json([{ id: 'u-owner', display_name: 'Sam', role: 'owner' }, { id: 'u-kid', display_name: 'Robin', role: 'child' }]);
    return Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  }));
}

const page = () => render(
  <MemoryRouter initialEntries={['/settings/permissions/modes']}>
    <Routes><Route path="/settings/:section/:tab?" element={<PermissionsPage />} /></Routes>
  </MemoryRouter>,
);

beforeEach(() => {
  calls = [];
  modes = [mode('*', 'ask'), mode('agent:notes-helper', 'remember')];
  session.signIn.mockClear();
  session.logout.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

it('lists the household default, each agent and person, and exempts the owner', async () => {
  gateway(() => Response.json({}));
  page();
  const list = await screen.findByRole('list', { name: 'Permission modes' });
  expect(within(list).getByText('Household default')).toBeVisible();
  expect(screen.getByLabelText('Mode for notes-helper')).toHaveValue('remember');
  expect(screen.getByLabelText('Mode for Robin')).toHaveValue('ask');
  expect(within(list).getByText(/follows the household default/)).toBeVisible();
  expect(screen.queryByLabelText('Mode for Sam')).toBeNull();
  expect(screen.getByText('Owner: runs directly')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Modes' })).toHaveAttribute('aria-current', 'page');
});

it('tightens at once with no passkey and says so', async () => {
  gateway((c) => Response.json(mode(decodeURIComponent(c.path.split('/').pop()!), 'locked')));
  page();
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText('Mode for notes-helper'), 'locked');
  await user.type(screen.getByLabelText(/Why/), 'acting up');
  await user.click(screen.getByRole('button', { name: 'Change mode' }));
  expect(await screen.findByText('notes-helper is now on Locked.')).toBeVisible();
  const put = calls.find((c) => c.method === 'PUT')!;
  expect(put.path).toBe('/v1/permission-modes/agent%3Anotes-helper');
  expect(put.body).toEqual({ mode: 'locked', reason: 'acting up' });
  expect(session.loginPasskey).not.toHaveBeenCalled();
});

it('loosening asks for the passkey only when the gateway does, then sends it again on the fresh session', async () => {
  gateway((c) => c.auth === 'Bearer old-session'
    ? Response.json({ error: 'unauthenticated', message: 'sign in again with your passkey to do this', reason: 'step_up_required' }, { status: 401 })
    : Response.json(mode('agent:notes-helper', 'auto')));
  page();
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText('Mode for notes-helper'), 'auto');
  expect(screen.getByText(/do more without asking you/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Confirm with passkey' }));
  expect(await screen.findByText('notes-helper is now on Auto within rules.')).toBeVisible();
  const puts = calls.filter((c) => c.method === 'PUT');
  expect(puts.map((c) => c.auth)).toEqual(['Bearer old-session', 'Bearer fresh-session']);
  expect(session.signIn).toHaveBeenCalledWith('fresh-session');
  expect(session.logout).toHaveBeenCalled();
});

it('explains a refusal in plain words and keeps the dialog open', async () => {
  modes = [mode('*', 'ask', false, false)];
  gateway(() => Response.json({ error: 'conflict', message: 'add a passkey first', reason: 'no_owner_passkey' }, { status: 409 }));
  page();
  expect(await screen.findByText(/No owner passkey yet/)).toBeVisible();
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText('Mode for Robin'), 'auto');
  await user.click(screen.getByRole('button', { name: 'Confirm with passkey' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Add a passkey first');
});

it('opens permission tabs and rules from notification links, and nothing else', () => {
  expect(toRoute('/settings/permissions/rules/pol_abc')).toBe('/settings/permissions/rules/pol_abc');
  expect(toRoute('/settings/permissions/auto-approved')).toBe('/settings/permissions/auto-approved');
  expect(toRoute('/settings/permissions/rules/a%2F..')).toBe('/settings/permissions');
});
