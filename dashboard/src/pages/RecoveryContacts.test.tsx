// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { RecoveryContacts } from './RecoveryContacts';

const state = vi.hoisted(() => ({ role: 'owner', signOut: vi.fn() }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture' }), useSession: () => ({ signOut: state.signOut }) }));
vi.mock('../shell/Shell', () => ({ useShell: () => ({ role: state.role }) }));
afterEach(() => vi.unstubAllGlobals());

const contact = {
  id: 'rc_1', role: 'recovery', kind: 'outside', display_name: 'Ana', household_user_id: null, state: 'cooling_off',
  invited_at: '2026-11-25T00:00:00Z', invite_expires_at: '2026-12-02T00:00:00Z', cooling_off_days: 7,
  accepted_at: '2026-11-25T01:00:00Z', usable_at: '2026-12-02T01:00:00Z', ended_at: null, device_label: 'phone',
  key_kind: 'hardware-reported', key_fingerprint: 'sha256:aa', last_seen_at: null,
};
const waits = { values: { cooling_off_days: 7 }, defaults: { cooling_off_days: 7 }, options: { cooling_off_days: [3, 7, 14] }, updated_at: null };

function gateway(handler: (method: string, path: string, body: unknown) => Response) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({ method: init.method ?? 'GET', path, body });
    return handler(init.method ?? 'GET', path, body);
  }));
  return calls;
}

it('lists real contacts, invites one and shows the signed invite once', async () => {
  state.role = 'owner';
  const calls = gateway((method, path) => {
    if (path === '/v1/auth/recovery/settings') return Response.json(waits);
    if (method === 'POST') return Response.json({ ...contact, id: 'rc_2', display_name: 'Ben', state: 'invited', invite: 'omri1.p.s', box_key_fingerprint: 'sha256:box' }, { status: 201 });
    return Response.json([contact]);
  });
  render(<RecoveryContacts />);
  expect(await screen.findByText('Ana')).toBeVisible();
  expect(screen.getByText(/Accepted, not counting yet/)).toBeVisible();
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Name'), 'Ben');
  await user.selectOptions(screen.getByLabelText('Cooling-off for this contact'), '14');
  await user.click(screen.getByRole('button', { name: 'Invite' }));
  expect(await screen.findByLabelText('Invite text')).toHaveValue('omri1.p.s');
  expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ kind: 'outside', display_name: 'Ben', cooling_off_days: 14 });
});

it('explains the passkey step-up instead of failing silently, and removes without one', async () => {
  state.role = 'owner';
  const calls = gateway((method, path) => {
    if (path === '/v1/auth/recovery/settings') return Response.json(waits);
    if (method === 'POST') return Response.json({ error: 'unauthenticated', message: 'sign in again', reason: 'step_up_required' }, { status: 401 });
    if (method === 'DELETE') return Response.json({ ...contact, state: 'removed' });
    return Response.json([contact]);
  });
  render(<RecoveryContacts />);
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Name'), 'Ben');
  await user.click(screen.getByRole('button', { name: 'Invite' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('fresh passkey sign-in');
  await user.click(screen.getByRole('button', { name: 'Remove Ana' }));
  expect(calls.some((c) => c.method === 'DELETE' && c.path === '/v1/auth/recovery/contacts/rc_1')).toBe(true);
});

it('shows a household adult the invitations addressed to them and nothing to manage', async () => {
  state.role = 'adult';
  const calls = gateway(() => Response.json([{ id: 'rc_3', role: 'recovery', owner_display_name: 'Zeus', invite_expires_at: '2026-12-02T00:00:00Z', cooling_off_days: 7 }]));
  render(<RecoveryContacts />);
  expect(await screen.findByText(/Zeus asked you to be a recovery contact/)).toBeVisible();
  expect(screen.queryByLabelText('Name')).toBeNull();
  expect(calls.every((c) => c.path === '/v1/auth/recovery/invitations')).toBe(true);
});
