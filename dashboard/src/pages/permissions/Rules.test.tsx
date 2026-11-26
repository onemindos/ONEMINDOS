// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PermissionsPage } from './PermissionsPage';

const session = vi.hoisted(() => ({
  signIn: vi.fn(async () => undefined),
  loginPasskey: vi.fn(async () => ({ access_token: 'fresh-session' })),
}));
vi.mock('../../session', () => ({
  useSession: () => ({ signOut: vi.fn() }),
  useSignedIn: () => ({ token: 'old-session', signIn: session.signIn, api: { logout: vi.fn(async () => undefined) },
    anon: { loginOptions: async () => ({ publicKey: {} }), loginPasskey: session.loginPasskey } }),
}));
vi.mock('../../shell/Shell', () => ({ useShell: () => ({ role: 'owner' }) }));
vi.mock('../../lib/webauthn', () => ({ webauthnSupported: () => true, getPasskey: vi.fn(async () => ({ id: 'cred' })) }));

const rule = (id: string, extra: Record<string, unknown> = {}) => ({
  id, revision: 1, name: null, allow: { types: ['backup.run'], requested_by: ['agent:helper'], params: {} },
  limits: { per_day: 10, max_uses: null, bytes_per_day: null, items_per_day: null }, window_id: null, principals: {},
  expires_at: '2027-01-30T00:00:00Z', forever: false, notify_after: 'digest', lapse_unused_days: 14, target: null,
  accept_injection_risk: false, created_from: null, created_by: { id: 'owner', kind: 'person' }, created_at: '2026-11-01T00:00:00Z',
  state: 'active', suspended_reason: null, revoked_at: null, revoked_by: null, uses: 3, last_used_at: '2026-11-20T00:00:00Z',
  uses_24h: 1, review_due: false, modes: { 'agent:helper': 'auto' }, ...extra,
});

type Call = { method: string; path: string; search: string; body?: unknown; auth: string | null };
let calls: Call[] = [];
let rules: Array<Record<string, unknown>> = [];
let answer: (c: Call) => Response | undefined = () => undefined;

beforeEach(() => {
  calls = [];
  answer = () => undefined;
  rules = [
    rule('pol_dated'),
    rule('pol_forever', { forever: true, expires_at: null, review_due: true, allow: { types: ['notes.read'], requested_by: ['agent:reader'], params: { vault: { const: 'home' } } }, modes: { 'agent:reader': 'ask' } }),
    rule('pol_held', { state: 'suspended', suspended_reason: 'token_rotated' }),
    rule('pol_old', { state: 'revoked', revoked_at: '2026-11-10T00:00:00Z' }),
  ];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const u = new URL(url);
    const call = { method: init.method ?? 'GET', path: u.pathname, search: u.search, body: init.body ? JSON.parse(String(init.body)) : undefined,
      auth: new Headers(init.headers).get('Authorization') };
    calls.push(call);
    const special = answer(call);
    if (special) return special;
    if (call.path === '/v1/approval-policies' && call.method === 'GET') return Response.json(rules);
    if (call.path === '/v1/audit/events') return Response.json([
      { seq: 1, ts: '2026-11-01T00:00:00Z', event: 'automation.policy.created', principal: { id: 'owner' }, action_id: null, data: { policy_id: 'pol_held', revision: 1 }, prev_hash: '', hash: '' },
      { seq: 2, ts: '2026-11-02T00:00:00Z', event: 'approval.policy.revised', principal: { id: 'owner' }, action_id: null, data: { policy_id: 'pol_other', revision: 2 }, prev_hash: '', hash: '' },
      { seq: 3, ts: '2026-11-03T00:00:00Z', event: 'approval.policy.suspended', principal: null, action_id: null, data: { policy_id: 'pol_held', reason: 'token_rotated' }, prev_hash: '', hash: '' },
    ]);
    if (call.method !== 'GET') return Response.json(rule('pol_held'));
    return Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  }));
});
afterEach(() => vi.unstubAllGlobals());

const page = (path: string) => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/settings/:section/:tab?/:item?" element={<PermissionsPage />} /></Routes>
  </MemoryRouter>,
);

it('lists rules in force with forever rules first, their limits, uses and why one does nothing', async () => {
  page('/settings/permissions/rules');
  const list = await screen.findByRole('list', { name: 'Rules in force' });
  const cards = within(list).getAllByRole('article');
  expect(cards).toHaveLength(3);
  expect(within(cards[0]!).getByText('Forever')).toBeVisible();
  expect(within(cards[0]!).getByText('Review due')).toBeVisible();
  expect(within(cards[0]!).getAllByText('reader may notes.read (vault = home)').length).toBeGreaterThan(0);
  expect(within(cards[0]!).getByText(/Not in use: reader is on Always ask/)).toBeVisible();
  expect(within(cards[1]!).getByText(/Ends .* · ends early if unused for 14 days · up to 10 a day/)).toBeVisible();
  expect(within(cards[1]!).getByText(/Used 3 times \(1 in the last 24 hours\)/)).toBeVisible();
  expect(within(cards[2]!).getByText(/Suspended because its key was replaced/)).toBeVisible();
  expect(screen.getByText('Ended rules (1)')).toBeVisible();
});

it('revokes with one tap and no passkey', async () => {
  page('/settings/permissions/rules');
  const user = userEvent.setup();
  const [first] = await screen.findAllByRole('button', { name: 'Revoke helper may backup.run' });
  await user.click(first!);
  expect(await screen.findByRole('status')).toHaveTextContent('It will not approve anything again.');
  const post = calls.find((c) => c.method === 'POST')!;
  expect(post.path).toBe('/v1/approval-policies/pol_dated/revoke');
  expect(session.loginPasskey).not.toHaveBeenCalled();
});

it('shows one rule with its own history, narrows it on the revision read, and re-confirms with the passkey', async () => {
  answer = (c) => c.path.endsWith('/reconfirm') && c.auth === 'Bearer old-session'
    ? Response.json({ error: 'unauthenticated', message: 'sign in again', reason: 'step_up_required' }, { status: 401 }) : undefined;
  page('/settings/permissions/rules/pol_held');
  const historyList = await screen.findByRole('list', { name: 'Rule history' });
  expect(within(historyList).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
    expect.stringContaining('Created (revision 1) by owner'),
    expect.stringContaining('Suspended: its key was replaced'),
  ]);
  expect(calls.find((c) => c.path === '/v1/audit/events')!.search).toContain('event=automation.policy.created%2Capproval.policy.*');
  const user = userEvent.setup();
  await user.clear(screen.getByLabelText('Uses per day'));
  await user.type(screen.getByLabelText('Uses per day'), '4');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('Saved as a new revision.')).toBeVisible();
  expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ limits: { per_day: 4 }, revision: 1 });
  await user.click(screen.getByRole('button', { name: 'Re-confirm with passkey' }));
  expect(await screen.findByText('Re-confirmed. The rule works again.')).toBeVisible();
  expect(calls.filter((c) => c.path.endsWith('/reconfirm')).map((c) => c.auth)).toEqual(['Bearer old-session', 'Bearer fresh-session']);
});

it('says so when a linked rule is gone', async () => {
  page('/settings/permissions/rules/pol_missing');
  expect(await screen.findByText(/This rule no longer exists/)).toBeVisible();
});
