// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PermissionsPage } from './PermissionsPage';

const shell = vi.hoisted(() => ({ role: 'owner' as string | undefined }));
const session = vi.hoisted(() => ({ loginPasskey: vi.fn(async () => ({ access_token: 'fresh-session' })) }));
vi.mock('../../session', () => ({
  useSession: () => ({ signOut: vi.fn() }),
  useSignedIn: () => ({ token: 'old-session', signIn: vi.fn(async () => undefined), api: { logout: vi.fn(async () => undefined) },
    anon: { loginOptions: async () => ({ publicKey: {} }), loginPasskey: session.loginPasskey } }),
}));
vi.mock('../../shell/Shell', () => ({ useShell: () => ({ role: shell.role }) }));
vi.mock('../../lib/webauthn', () => ({ webauthnSupported: () => true, getPasskey: vi.fn(async () => ({ id: 'cred' })) }));

type Call = { method: string; path: string; body?: unknown; auth: string | null };
let calls: Call[] = [];
let denies: Array<Record<string, unknown>> = [];

beforeEach(() => {
  shell.role = 'owner';
  calls = [];
  session.loginPasskey.mockClear();
  denies = [{ id: 'den_1', principal: 'agent:helper', action_type: null, tier: 'T3', reason: 'never delete', created_by: { id: 'owner' }, created_at: '2026-11-01T00:00:00Z' }];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const call = { method: init.method ?? 'GET', path: new URL(url).pathname, body: init.body ? JSON.parse(String(init.body)) : undefined,
      auth: new Headers(init.headers).get('Authorization') };
    calls.push(call);
    if (call.path === '/v1/approval-denies' && call.method === 'GET') return Response.json(denies);
    if (call.path === '/v1/approval-denies' && call.method === 'POST') {
      const row = { id: 'den_2', created_by: { id: 'owner' }, created_at: '2026-11-02T00:00:00Z', action_type: null, tier: null, reason: null, ...(call.body as object) };
      denies = [...denies, row];
      return Response.json(row, { status: 201 });
    }
    if (call.method === 'DELETE') {
      if (call.auth === 'Bearer old-session') return Response.json({ error: 'unauthenticated', message: 'sign in again', reason: 'step_up_required' }, { status: 401 });
      denies = [];
      return new Response(null, { status: 204 });
    }
    if (call.path === '/v1/agents') return Response.json([{ id: 'helper', budget_per_day: 1, used_24h: 0, pending_approvals: 0, cancelled: false }]);
    if (call.path === '/v1/actions') return Response.json([]);
    return Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  }));
});
afterEach(() => vi.unstubAllGlobals());

const page = () => render(
  <MemoryRouter initialEntries={['/settings/permissions/never']}>
    <Routes><Route path="/settings/:section/:tab?/:item?" element={<PermissionsPage />} /></Routes>
  </MemoryRouter>,
);

it('lists never rules in words and adds one for a request type with no passkey', async () => {
  page();
  expect(await screen.findByText(/may never: Deleting things \(T3\)/)).toBeVisible();
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Who'), 'agent:helper');
  await user.click(screen.getByLabelText('One request type'));
  await user.type(screen.getByLabelText('Request type'), 'app.install');
  await user.type(screen.getByLabelText('Why (optional)'), 'ask me');
  await user.click(screen.getByRole('button', { name: 'Add never rule' }));
  expect(await screen.findByRole('status')).toHaveTextContent('helper can no longer have that approved without you.');
  expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ principal: 'agent:helper', action_type: 'app.install', reason: 'ask me' });
  expect(session.loginPasskey).not.toHaveBeenCalled();
  expect(await screen.findByText(/may never: app.install/)).toBeVisible();
  expect(screen.getByLabelText('Who')).toHaveValue(''); // cleared, so a second press sends nothing twice
  expect(screen.getByLabelText('Request type')).toHaveValue('');
  expect(screen.getByLabelText('Why (optional)')).toHaveValue('');
});

it('keeps the form when adding fails', async () => {
  const real = fetch;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => (init.method === 'POST'
    ? Response.json({ error: 'permission_denied', message: 'not yours' }, { status: 403 }) : real(url, init))));
  page();
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Who'), 'agent:other');
  await user.click(screen.getByRole('button', { name: 'Add never rule' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('You are not allowed to change this.');
  expect(screen.getByLabelText('Who')).toHaveValue('agent:other');
});

it('removing one loosens: it asks first, and nothing is sent on Cancel', async () => {
  page();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove: helper may never Deleting things (T3)' }));
  const dialog = screen.getByRole('alertdialog');
  expect(dialog).toHaveTextContent('Allow helper to have Deleting things (T3) approved again?');
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.queryByRole('alertdialog')).toBeNull();
  expect(calls.filter((c) => c.method === 'DELETE')).toHaveLength(0);
  expect(screen.getByText(/may never: Deleting things \(T3\)/)).toBeVisible();
});

it('does not offer Remove to anyone but the owner', async () => {
  shell.role = 'adult';
  page();
  expect(await screen.findByText(/may never: Deleting things \(T3\)/)).toBeVisible();
  expect(screen.queryByRole('button', { name: /^Remove/ })).toBeNull();
});

it('removing one, once confirmed, signs in with the passkey when the gateway asks', async () => {
  page();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove: helper may never Deleting things (T3)' }));
  await user.click(screen.getByRole('button', { name: 'Request removal' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Removed the rule for helper.');
  expect(calls.filter((c) => c.method === 'DELETE').map((c) => c.auth)).toEqual(['Bearer old-session', 'Bearer fresh-session']);
  expect(screen.getByText('No never rules yet.')).toBeVisible();
});

it('keeps a deny rule visible while its removal is awaiting approval', async () => {
  const gateway = fetch;
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => init.method === 'DELETE'
    ? Promise.resolve(Response.json({ id: 'act_deny', requested_by: { id: 'owner' }, state: 'awaiting_approval' }, { status: 202 }))
    : gateway(url, init)));
  page();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove: helper may never Deleting things (T3)' }));
  await user.click(screen.getByRole('button', { name: 'Request removal' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Removal requested for helper.');
  expect(screen.getByText(/may never: Deleting things/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'Review in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act_deny');
  expect(session.loginPasskey).not.toHaveBeenCalled();
});
