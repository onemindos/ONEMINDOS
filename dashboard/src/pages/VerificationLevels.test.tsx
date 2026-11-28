// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { OneMindError } from '@onemind/sdk';
import { offeredLevels, ownWaiting, requestErrorText, VerificationLevels, waitingChanges } from './VerificationLevels';

const state = vi.hoisted(() => ({ role: 'owner' as string | undefined, signOut: vi.fn() }));
// The shape a real gateway gives: no principal on the session, the account from GET /v1/me, the role from the shell.
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture', mock: false, principal: undefined, account: { id: 'zeus', kind: 'person', role: state.role }, signOut: state.signOut }), useSession: () => ({ signOut: state.signOut }) }));
vi.mock('../shell/Shell', () => ({ useShell: () => ({ role: state.role }) }));
vi.mock('../lib/webauthn', () => ({ getPasskey: vi.fn() }));
vi.mock('../lib/boxcode', () => ({ askBoxCode: vi.fn() }));
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); state.role = 'owner'; });

const row = (key: string, label: string, def: string, min: string, max = 'L3', strict = false) => ({ key, label, default: def, current: def, minimum: min, maximum: max, strict });
const rows = [
  row('data.access', 'Data access', 'L0', 'L0', 'L1'),
  row('tier.T3', 'Approve a destructive action', 'L2', 'L1'),
  row('tier.P', 'Approve a physical action', 'L2', 'L2', 'L3', true),
  row('verification.table', 'Change this table', 'L2', 'L2'),
];
const table = { rows, types: [], household_level: 'L2', grace: false, recovery_needed: false, box_confirm: true };

type Call = { method: string; path: string; body: unknown };
function gateway(route: (c: Call) => unknown) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const c = { method: init.method ?? 'GET', path: new URL(url).pathname, body: init.body ? JSON.parse(String(init.body)) : undefined };
    calls.push(c);
    const out = route(c);
    if (out instanceof Response) return out;
    return out === undefined ? Response.json({ error: 'not_found', message: 'no' }, { status: 404 }) : Response.json(out);
  }));
  return calls;
}
const mount = () => render(<MemoryRouter><VerificationLevels /></MemoryRouter>);

it('offers only levels between the floor and the ceiling, and L3 only when a key reaches it', () => {
  expect(offeredLevels({ minimum: 'L1', maximum: 'L3' }, 'L2')).toEqual(['L1', 'L2']);
  expect(offeredLevels({ minimum: 'L1', maximum: 'L3' }, 'L3')).toEqual(['L1', 'L2', 'L3']);
  expect(offeredLevels({ minimum: 'L2', maximum: 'L3' }, null)).toEqual(['L2']);
  // Data access never goes above L1: your files never depend on a strong key.
  expect(offeredLevels({ minimum: 'L0', maximum: 'L1' }, 'L3')).toEqual(['L0', 'L1']);
});

it('reads the waiting changes with who asked, and says refusals in plain words', () => {
  const me = { id: 'zeus', kind: 'person' };
  const w = waitingChanges([
    { type: 'verification.requirement.set', state: 'awaiting_approval', params: { key: 'tier.T3', level: 'L1' }, requested_by: me },
    { type: 'verification.requirement.set', state: 'awaiting_approval', params: { key: 'tier.T2', level: 'L0' }, requested_by: { id: 'gus', kind: 'person' } },
    { type: 'verification.requirement.set', state: 'succeeded', params: { key: 'tier.T1', level: 'L2' }, requested_by: me },
    { type: 'app.remove', state: 'awaiting_approval', params: { app_id: 'x' }, requested_by: me },
  ] as never, me);
  expect(w).toEqual({ 'tier.T3': [{ level: 'L1', by: 'you', mine: true }], 'tier.T2': [{ level: 'L0', by: 'gus', mine: false }] });
  expect(waitingChanges([{ type: 'verification.requirement.set', state: 'awaiting_approval', params: { key: 'tier.T2', level: 'L0' }, requested_by: { id: 'gus', kind: 'person' } }] as never,
    me, (id) => (id === 'gus' ? 'Gus' : undefined))['tier.T2']?.[0]?.by).toBe('Gus');
  expect(ownWaiting(w['tier.T3'])).toBe(true);
  expect(ownWaiting(w['tier.T2'])).toBe(false);
  // An agent with the same id as the owner is not the owner.
  expect(waitingChanges([{ type: 'verification.requirement.set', state: 'awaiting_approval', params: { key: 'tier.T3', level: 'L1' }, requested_by: { id: 'zeus', kind: 'agent' } }] as never, me))
    .toEqual({ 'tier.T3': [{ level: 'L1', by: 'agent zeus', mine: false }] });
  expect(requestErrorText(new OneMindError(409, 'conflict', 'x', { reason: 'level_unreachable' }))).toMatch(/no key on this box reaches L3/);
  expect(requestErrorText(new OneMindError(422, 'conflict', 'x', { reason: 'below_floor' }))).toMatch(/can't go that low/);
});

it('shows each row with its level, default and floor, and never offers a level below the floor', async () => {
  gateway(({ path }) => ({ '/v1/verification-requirements': table, '/v1/actions': [] } as Record<string, unknown>)[path]);
  mount();
  const destructive = (await screen.findByText('Approve a destructive action')).closest('tr')!;
  expect(within(destructive).getByText('Needs L2 · Proven key')).toBeVisible();
  expect(within(destructive).getByText(/Default L2 · lowest L1 · highest L3/)).toBeVisible();
  const select = within(destructive).getByLabelText('New level for Approve a destructive action');
  expect([...select.querySelectorAll('option')].map((o) => o.value)).toEqual(['L1', 'L2']);
  // The table's own row and the physical row sit at their floor with no stronger key: nothing to choose.
  const own = screen.getByText('Change this table').closest('tr')!;
  expect(within(own).queryByRole('combobox')).toBeNull();
  expect(screen.getByText('Approve a physical action').closest('tr')).toHaveTextContent('never eased before your first proven key');
});

it('files a change through Approvals, never a direct write', async () => {
  const calls = gateway(({ method, path }) => {
    if (path === '/v1/actions' && method === 'POST') return { id: 'act_1', state: 'awaiting_approval' };
    return ({ '/v1/verification-requirements': table, '/v1/actions': [], '/v1/instance': { now: new Date().toISOString() } } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  const destructive = (await screen.findByText('Approve a destructive action')).closest('tr')!;
  await user.selectOptions(within(destructive).getByLabelText('New level for Approve a destructive action'), 'L1');
  await user.click(within(destructive).getByRole('button', { name: 'Ask to change Approve a destructive action' }));
  expect(await screen.findByText(/It waits in Approvals for your proven key/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'Open Approvals' })).toHaveAttribute('href', '/approvals');
  const filed = calls.find((c) => c.method === 'POST');
  expect(filed?.path).toBe('/v1/actions');
  expect(filed?.body).toMatchObject({ type: 'verification.requirement.set', params: { key: 'tier.T3', level: 'L1' } });
  expect(calls.filter((c) => c.method !== 'GET' && c.path !== '/v1/actions')).toEqual([]);
});

it('shows a change already waiting instead of asking again, and the household state', async () => {
  gateway(({ path }) => ({
    '/v1/verification-requirements': { ...table, household_level: 'L1', grace: true, box_confirm: false },
    '/v1/actions': [{ id: 'a', type: 'verification.requirement.set', state: 'awaiting_approval', params: { key: 'tier.T3', level: 'L1' }, requested_by: { id: 'zeus', kind: 'person' } }],
  } as Record<string, unknown>)[path]);
  mount();
  expect(await screen.findByText('L1 asked by you · waits in Approvals')).toBeVisible();
  const destructive = screen.getByText('Approve a destructive action').closest('tr')!;
  expect(within(destructive).queryByRole('combobox')).toBeNull();
  expect(screen.getByText(/accept any passkey plus the code on the box's own screen/)).toBeVisible();
  expect(screen.getByText(/This box has no screen to show that code/)).toBeVisible();
});

it('raises one kind of request to L3 only when a key reaches it', async () => {
  const calls = gateway(({ method, path }) => {
    if (path === '/v1/actions' && method === 'POST') return { id: 'act_2' };
    return ({ '/v1/verification-requirements': { ...table, household_level: 'L3' }, '/v1/actions': [{ id: 'x', type: 'app.remove', state: 'succeeded', params: {} }] } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Kind of request'), 'app.remove');
  await user.selectOptions(screen.getByLabelText('Level'), 'L3');
  await user.click(screen.getByRole('button', { name: 'Ask for this check' }));
  await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({ params: { key: 'type:app.remove', level: 'L3' } }));
});

it('keeps L3 out of the choices while no key reaches it', async () => {
  gateway(({ path }) => ({ '/v1/verification-requirements': table, '/v1/actions': [] } as Record<string, unknown>)[path]);
  mount();
  const level = await screen.findByLabelText('Level');
  expect([...level.querySelectorAll('option')].map((o) => o.value)).toEqual(['L2']);
  expect(screen.getByText('L3 appears here once a key on this box reaches it.')).toBeVisible();
});

it('tells a non-owner the table is the owner\'s and reads nothing', async () => {
  state.role = 'adult';
  const calls = gateway(() => undefined);
  mount();
  expect(screen.getByRole('status')).toHaveTextContent('Only an owner');
  expect(calls).toEqual([]);
});

it('waits for the role from GET /v1/me instead of refusing the owner, and reads nothing yet', () => {
  state.role = undefined;
  const calls = gateway(() => undefined);
  mount();
  expect(screen.getByRole('status')).toHaveTextContent('Checking who is signed in');
  expect(screen.queryByText(/Only an owner/)).toBeNull();
  expect(calls).toEqual([]);
});

it('says a refusal of the table plainly instead of a raw error', async () => {
  gateway(({ path }) => (path === '/v1/verification-requirements' ? Response.json({ error: 'permission_denied', message: 'owner only' }, { status: 403 }) : path === '/v1/actions' ? [] : undefined));
  mount();
  expect(await screen.findByText('Your account is not allowed to see this.')).toBeVisible();
  expect(screen.queryByText(/OneMindError|\[object/)).toBeNull();
});

it('shows a guest\'s waiting downgrade as theirs and leaves the owner\'s own change open', async () => {
  // Any person may file a table change (core registers the type for every person). A guest asking to lower the
  // destructive row must not read as the owner's own request, nor take the owner's "Ask to change" away.
  const calls = gateway(({ method, path }) => {
    if (path === '/v1/actions' && method === 'POST') return { id: 'act_3' };
    return ({
      '/v1/verification-requirements': table,
      '/v1/actions': [{ id: 'g', type: 'verification.requirement.set', state: 'awaiting_approval', params: { key: 'tier.T3', level: 'L1' }, requested_by: { id: 'usr_gus', kind: 'person' } }],
      '/v1/users': [{ id: 'zeus', display_name: 'Zeus', role: 'owner' }, { id: 'usr_gus', display_name: 'Gus', role: 'guest' }],
      '/v1/instance': { now: new Date().toISOString() },
    } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  expect(await screen.findByText('L1 asked by Gus · waits in Approvals')).toBeVisible();
  expect(screen.queryByText(/asked by you/)).toBeNull();
  const destructive = screen.getByText('Approve a destructive action').closest('tr')!;
  const select = within(destructive).getByLabelText('New level for Approve a destructive action');
  await user.selectOptions(select, 'L1');
  await user.click(within(destructive).getByRole('button', { name: 'Ask to change Approve a destructive action' }));
  await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({ params: { key: 'tier.T3', level: 'L1' } }));
});

it('keeps a refused kind of request in the field so it can be corrected', async () => {
  gateway(({ method, path }) => {
    if (path === '/v1/actions' && method === 'POST') return Response.json({ error: 'conflict', message: 'unknown', reason: 'unknown_row' }, { status: 422 });
    return ({ '/v1/verification-requirements': table, '/v1/actions': [], '/v1/instance': { now: new Date().toISOString() } } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  const field = await screen.findByLabelText('Kind of request');
  await user.type(field, 'app.remov');
  await user.click(screen.getByRole('button', { name: 'Ask for this check' }));
  expect(await screen.findByText(/doesn't know that kind of request/)).toBeVisible();
  expect(field).toHaveValue('app.remov');
});

it('signs out when the sign-in lapsed while filing a change', async () => {
  gateway(({ method, path }) => {
    if (path === '/v1/actions' && method === 'POST') return Response.json({ error: 'unauthenticated', message: 'expired' }, { status: 401 });
    return ({ '/v1/verification-requirements': table, '/v1/actions': [], '/v1/instance': { now: new Date().toISOString() } } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  const destructive = (await screen.findByText('Approve a destructive action')).closest('tr')!;
  await user.selectOptions(within(destructive).getByLabelText('New level for Approve a destructive action'), 'L1');
  await user.click(within(destructive).getByRole('button', { name: 'Ask to change Approve a destructive action' }));
  await waitFor(() => expect(state.signOut).toHaveBeenCalled());
});
