// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { OneMindError } from '@onemind/sdk';
import { offeredLevels, requestErrorText, VerificationLevels, waitingChanges } from './VerificationLevels';

const state = vi.hoisted(() => ({ role: 'owner' }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture', mock: false, principal: { id: 'zeus', kind: 'person', role: state.role } }), useSession: () => ({ signOut: vi.fn() }) }));
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

it('reads the waiting changes and says refusals in plain words', () => {
  expect(waitingChanges([
    { type: 'verification.requirement.set', state: 'awaiting_approval', params: { key: 'tier.T3', level: 'L1' } },
    { type: 'verification.requirement.set', state: 'succeeded', params: { key: 'tier.T1', level: 'L2' } },
    { type: 'app.remove', state: 'awaiting_approval', params: { app_id: 'x' } },
  ] as never)).toEqual({ 'tier.T3': 'L1' });
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
    '/v1/actions': [{ id: 'a', type: 'verification.requirement.set', state: 'awaiting_approval', params: { key: 'tier.T3', level: 'L1' } }],
  } as Record<string, unknown>)[path]);
  mount();
  expect(await screen.findByText('L1 waits in Approvals')).toBeVisible();
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
