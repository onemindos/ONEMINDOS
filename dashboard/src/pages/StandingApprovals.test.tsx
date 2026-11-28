// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { buildPolicy, StandingApprovals } from './StandingApprovals';

const state = vi.hoisted(() => ({ role: 'owner' as string | undefined, signOut: vi.fn() }));
// The shape a real gateway gives: no principal on the session, the account from GET /v1/me, the role from the shell.
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture', mock: false, principal: undefined, account: { id: 'zeus', kind: 'person', role: state.role }, signOut: state.signOut }), useSession: () => ({ signOut: state.signOut }) }));
vi.mock('../shell/Shell', () => ({ useShell: () => ({ role: state.role }) }));
const webauthn = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../lib/webauthn', () => ({ getPasskey: webauthn.get }));
const box = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock('../lib/boxcode', () => ({ askBoxCode: box.ask }));
beforeEach(() => { webauthn.get.mockResolvedValue({ id: 'bio' }); box.ask.mockResolvedValue('482913'); });
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); state.role = 'owner'; });

type Call = { method: string; path: string; body: unknown; headers: Record<string, string> };
function gateway(route: (c: Call) => unknown) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const c = { method: init.method ?? 'GET', path: decodeURIComponent(new URL(url).pathname), body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: (init.headers ?? {}) as Record<string, string> };
    calls.push(c);
    const out = route(c);
    if (out === 204) return new Response(null, { status: 204 });
    if (out instanceof Response) return out;
    return out === undefined ? Response.json({ error: 'not_found', message: 'no' }, { status: 404 }) : Response.json(out);
  }));
  return calls;
}
const stepUp = (op: string, target: string, body: unknown, box?: string) => Response.json({ error: 'unauthenticated', message: 'confirm it is you', reason: 'step_up_required',
  details: [{ step_up: { op, target, body, required_level: 'L2', ...(box ? { box } : {}) } }] }, { status: 401 });
const pol = (id: string, extra: object = {}) => ({ id, revision: 1, name: 'Nightly restarts', allow: { types: ['app.restart'], requested_by: ['agent:hermes'], params: {} },
  limits: { per_day: 3 }, window_id: null, expires_at: '2026-12-20T00:00:00Z', created_by: { kind: 'person', id: 'zeus' }, created_at: '2026-11-20T00:00:00Z',
  state: 'active', uses_24h: 1, ...extra });
const reads = (path: string, policies: unknown[]) => ({
  '/v1/approval-policies': policies, '/v1/agents': [{ id: 'agent:hermes' }], '/v1/automation/rules': [{ id: 'rul_1', name: 'Restart on crash' }],
  '/v1/windows': [{ id: 'win_nightly', name: 'Nightly' }],
} as Record<string, unknown>)[path];
const mount = () => render(<MemoryRouter><StandingApprovals /></MemoryRouter>);

it('builds a narrow, expiring body and refuses what the hub would refuse', () => {
  const now = Date.parse('2026-11-26T00:00:00Z');
  const ok = { name: ' Nightly ', types: 'app.restart, app.restart', from: 'agent:hermes', perDay: '3', days: '30', window: 'win_nightly', params: '{"app_id": {"enum": ["notes"]}}' };
  expect(buildPolicy(ok, now)).toEqual({ name: 'Nightly', allow: { types: ['app.restart'], requested_by: ['agent:hermes'], params: { app_id: { enum: ['notes'] } } },
    limits: { per_day: 3 }, window_id: 'win_nightly', expires_at: '2026-12-26T00:00:00.000Z' });
  expect(buildPolicy({ ...ok, from: 'agent:*' }, now)).toMatch(/exactly/);
  expect(buildPolicy({ ...ok, days: '91' }, now)).toMatch(/1 to 90 days/);
  expect(buildPolicy({ ...ok, perDay: '0' }, now)).toMatch(/1 to 1000/);
  expect(buildPolicy({ ...ok, types: ' ' }, now)).toMatch(/which kind of request/);
  expect(buildPolicy({ ...ok, params: '[1]' }, now)).toMatch(/JSON object/);
});

it('lists standing approvals with what they cover, who may ask and today\'s use', async () => {
  gateway(({ path }) => reads(path, [pol('pol_1')]));
  mount();
  const row = (await screen.findByText('Nightly restarts')).closest('tr')!;
  expect(within(row).getByText('Covers app.restart')).toBeVisible();
  expect(within(row).getByText('agent:hermes')).toBeVisible();
  expect(within(row).getByText('1 of 3')).toBeVisible();
  expect(within(row).getByText('On')).toBeVisible();
});

it('creates one with the proven key the hub names (step-up in place)', async () => {
  let made = false;
  const calls = gateway(({ method, path, headers, body }) => {
    if (path === '/v1/approval-policies' && method === 'POST') {
      if (headers['OneMind-Step-Up'] !== 'grant-p') return stepUp('approvals.policies.create', '', body);
      made = true; return pol('pol_2');
    }
    if (path === '/v1/auth/step-up/options') return { challenge_id: 's', expires_at: '2026-11-26T12:00:00Z', required_level: 'L2', grace: false, publicKey: { challenge: 'p' } };
    if (path === '/v1/auth/step-up') return { step_up: 'grant-p', expires_at: '2026-11-26T12:02:00Z', level: 'L2' };
    return reads(path, made ? [pol('pol_2')] : []);
  });
  mount();
  const user = userEvent.setup();
  expect(await screen.findByText('None yet. Every request waits for you in Approvals.')).toBeVisible();
  await user.type(screen.getByLabelText(/Kinds of request it covers/), 'app.restart');
  await user.type(screen.getByLabelText(/Who may ask/), 'agent:hermes');
  await user.selectOptions(screen.getByLabelText('Only during'), 'win_nightly');
  await user.click(screen.getByRole('button', { name: 'Create standing approval' }));
  expect(await screen.findByText('Standing approval created.')).toBeVisible();
  const opts = calls.find((c) => c.path === '/v1/auth/step-up/options')?.body as { op: string; body: { allow: unknown; window_id: string } };
  expect(opts.op).toBe('approvals.policies.create');
  expect(opts.body).toMatchObject({ allow: { types: ['app.restart'], requested_by: ['agent:hermes'] }, window_id: 'win_nightly', limits: { per_day: 3 } });
  expect(webauthn.get).toHaveBeenCalledWith({ challenge: 'p' });
});

it('shows why a body is refused before anything is sent', async () => {
  const calls = gateway(({ path }) => reads(path, []));
  mount();
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText(/Kinds of request it covers/), 'app.restart');
  await user.type(screen.getByLabelText(/Who may ask/), 'agent:*');
  await user.click(screen.getByRole('button', { name: 'Create standing approval' }));
  expect(await screen.findByText(/Name each agent or automation exactly/)).toBeVisible();
  expect(calls.filter((c) => c.method !== 'GET')).toEqual([]);
});

it('turns a paused one back on with the box code before the first proven key', async () => {
  let on = false;
  const calls = gateway(({ method, path, headers }) => {
    if (path === '/v1/approval-policies/pol_1/confirm') {
      if (headers['OneMind-Step-Up'] !== 'grant-c') return stepUp('approvals.policies.confirm', 'pol_1', {}, 'required');
      on = true; return pol('pol_1');
    }
    if (path === '/v1/auth/step-up/options') return { challenge_id: 's', expires_at: '2026-11-26T12:00:00Z', required_level: 'L1', grace: true, box_code_required: true, publicKey: { challenge: 'c' } };
    if (path === '/v1/auth/step-up') return { step_up: 'grant-c', expires_at: '2026-11-26T12:02:00Z', level: 'L1' };
    void method;
    return reads(path, [pol('pol_1', on ? {} : { state: 'paused' })]);
  });
  mount();
  const user = userEvent.setup();
  expect(await screen.findByText('Paused: confirm it')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Turn Nightly restarts back on' }));
  expect(await screen.findByText('Nightly restarts is on again.')).toBeVisible();
  expect(box.ask).toHaveBeenCalledWith('approvals.policies.confirm');
  expect(calls.find((c) => c.path === '/v1/auth/step-up')?.body).toEqual({ credential: { id: 'bio' }, box_code: '482913' });
});

it('removes one only after a second click, with no step-up', async () => {
  let gone = false;
  const calls = gateway(({ method, path }) => {
    if (method === 'DELETE' && path === '/v1/approval-policies/pol_1') { gone = true; return 204; }
    return reads(path, gone ? [] : [pol('pol_1')]);
  });
  mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove Nightly restarts' }));
  expect(gone).toBe(false);
  await user.click(screen.getByRole('button', { name: 'Confirm remove Nightly restarts' }));
  await waitFor(() => expect(gone).toBe(true));
  expect(await screen.findByText(/removed. Its requests wait for you again/)).toBeVisible();
  expect(calls.some((c) => c.path.startsWith('/v1/auth/step-up'))).toBe(false);
});

it('waits for the role from GET /v1/me instead of refusing the owner, and reads nothing yet', () => {
  state.role = undefined;
  const calls = gateway(() => undefined);
  mount();
  expect(screen.getByRole('status')).toHaveTextContent('Checking who is signed in');
  expect(screen.queryByText(/Only an owner/)).toBeNull();
  expect(calls).toEqual([]);
});

it('tells a non-owner the rules are the owner\'s and reads nothing', () => {
  state.role = 'adult';
  const calls = gateway(() => undefined);
  mount();
  expect(screen.getByRole('status')).toHaveTextContent('Only an owner');
  expect(calls).toEqual([]);
});

it('shows when each one ends and its window in the Name cell, which a 390 px phone keeps', async () => {
  gateway(({ path }) => reads(path, [pol('pol_1', { window_id: 'win_nightly', state: 'paused' })]));
  mount();
  const row = (await screen.findByText('Nightly restarts')).closest('tr')!;
  const name = row.querySelector('td')!;
  expect(within(name).getByText(/^Ends .+ · Nightly$/)).toBeVisible();
  // The Ends column is not one the compact table hides.
  const ends = row.querySelector('td[data-label="Ends"]')!;
  expect(ends).toHaveTextContent('20 Dec 2026');
  expect(ends).not.toHaveClass('om-secondary');
});

it('says when the windows or the requesters could not be loaded instead of a silent "Any time"', async () => {
  gateway(({ path }) => (path === '/v1/windows' || path === '/v1/agents'
    ? Response.json({ error: 'internal', message: 'down' }, { status: 500 }) : reads(path, [])));
  mount();
  expect(await screen.findByText(/Couldn’t load the maintenance windows/)).toBeVisible();
  expect(screen.getByText(/Couldn’t load the agents and automations/)).toBeVisible();
});

it('signs out when the sign-in lapsed while removing one', async () => {
  gateway(({ method, path }) => (method === 'DELETE' ? Response.json({ error: 'unauthenticated', message: 'unknown token' }, { status: 401 }) : reads(path, [pol('pol_1')])));
  mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove Nightly restarts' }));
  await user.click(screen.getByRole('button', { name: 'Confirm remove Nightly restarts' }));
  await waitFor(() => expect(state.signOut).toHaveBeenCalled());
});
