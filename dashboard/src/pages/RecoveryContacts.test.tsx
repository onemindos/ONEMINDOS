// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { RecoveryContacts } from './RecoveryContacts';

const state = vi.hoisted(() => ({ role: 'owner', signOut: vi.fn() }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture' }), useSession: () => ({ signOut: state.signOut }) }));
vi.mock('../shell/Shell', () => ({ useShell: () => ({ role: state.role }) }));
afterEach(() => {
  vi.unstubAllGlobals();
  handlesLegacy = false;
});

const contact = {
  id: 'rc_1', role: 'recovery', kind: 'outside', display_name: 'Ana', household_user_id: null, state: 'cooling_off',
  invited_at: '2026-11-25T00:00:00Z', invite_expires_at: '2026-12-02T00:00:00Z', cooling_off_days: 7,
  accepted_at: '2026-11-25T01:00:00Z', usable_at: '2026-12-02T01:00:00Z', ended_at: null, device_label: 'phone',
  key_kind: 'hardware-reported', key_fingerprint: 'sha256:aa', last_seen_at: null,
};
let handlesLegacy = false;
const waits = { values: { cooling_off_days: 7 }, defaults: { cooling_off_days: 7 }, options: { cooling_off_days: [3, 7, 14] }, updated_at: null };

function gateway(handler: (method: string, path: string, body: unknown) => Response) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const legacyEmpty = (path: string) => path.startsWith('/v1/auth/legacy/');
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({ method: init.method ?? 'GET', path, body });
    // Tests written before legacy contacts (25f) see an empty legacy list unless they answer it themselves.
    const answer = handler(init.method ?? 'GET', path, body);
    return legacyEmpty(path) && !handlesLegacy ? Response.json([]) : answer;
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

it('queues the legacy invite for review and shows the signed invite only after approval', async () => {
  state.role = 'owner';
  handlesLegacy = true;
  let approved = false;
  const legacyContact = { ...contact, id: 'rc_9', role: 'legacy', state: 'invited', display_name: 'Legacy recipient', wait_days: 60 };
  const calls = gateway((method, path) => {
    if (path === '/v1/auth/legacy/contacts' && method === 'POST') {
      return Response.json({ action_id: 'approval-9', contact_id: 'rc_9', wait_days: 60 }, { status: 202 });
    }
    if (path === '/v1/auth/legacy/contacts') return Response.json(approved ? [legacyContact] : []);
    if (path === '/v1/auth/legacy/contacts/rc_9/invite' && approved) {
      return Response.json({ ...legacyContact, invite: 'omri1.p.s', box_key_fingerprint: 'sha256:box' });
    }
    if (path === '/v1/auth/recovery/settings') return Response.json(waits);
    return Response.json([]);
  });
  const user = userEvent.setup();
  const view = render(<MemoryRouter><RecoveryContacts legacyEnrollmentAvailable /></MemoryRouter>);
  await user.type(screen.getByLabelText('Legacy contact name'), 'Legacy recipient');
  await user.selectOptions(screen.getByLabelText('Claim wait'), '60');
  await user.click(screen.getByRole('button', { name: 'Request legacy invite' }));
  expect(await screen.findByRole('link', { name: 'Review legacy invite' })).toHaveAttribute('href', '/approvals?highlight=approval-9');
  expect(screen.queryByLabelText('Legacy invite text')).toBeNull();
  expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ kind: 'outside', display_name: 'Legacy recipient', wait_days: 60 });
  view.unmount();
  approved = true;
  render(<MemoryRouter><RecoveryContacts legacyEnrollmentAvailable /></MemoryRouter>);
  await user.click(await screen.findByRole('button', { name: 'Show legacy invite for Legacy recipient' }));
  expect(await screen.findByLabelText('Legacy invite text')).toHaveValue('omri1.p.s');
});

it('shows the legacy enrollment hold while allowing outstanding invites to be removed', async () => {
  state.role = 'owner';
  handlesLegacy = true;
  const legacyContact = { ...contact, id: 'rc_9', role: 'legacy', state: 'invited', display_name: 'Legacy recipient', wait_days: 60 };
  const calls = gateway((_method, path) => {
    if (path === '/v1/auth/recovery/settings') return Response.json(waits);
    if (path === '/v1/auth/legacy/contacts') return Response.json([legacyContact]);
    return Response.json([]);
  });
  render(<RecoveryContacts />);
  expect(screen.getByText(/Legacy contact enrollment is on hold/)).toBeVisible();
  const remove = await screen.findByRole('button', { name: 'Remove legacy contact Legacy recipient' });
  expect(screen.queryByRole('button', { name: 'Request legacy invite' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Show legacy invite for Legacy recipient' })).toBeNull();
  await userEvent.setup().click(remove);
  expect(calls.some((c) => c.method === 'DELETE' && c.path === '/v1/auth/legacy/contacts/rc_9')).toBe(true);
});

it('shows a household adult the invitations addressed to them and nothing to manage', async () => {
  state.role = 'adult';
  const calls = gateway(() => Response.json([{ id: 'rc_3', role: 'recovery', owner_display_name: 'Zeus', invite_expires_at: '2026-12-02T00:00:00Z', cooling_off_days: 7 }]));
  render(<RecoveryContacts />);
  expect(await screen.findByText(/Zeus asked you to be a recovery contact/)).toBeVisible();
  expect(screen.queryByLabelText('Name')).toBeNull();
  expect(calls.every((c) => c.path === '/v1/auth/recovery/invitations' || c.path === '/v1/auth/legacy/claims')).toBe(true);
});

it('shows a running recovery to an owner and stops it without a step-up; the waits come from the gateway', async () => {
  state.role = 'owner';
  const running = [{ id: 'rr_1', path: 'contact', state: 'waiting', created_at: '2026-11-25T00:00:00Z', vouch_expires_at: null, vouched_at: '2026-11-25T00:01:00Z', vouch_method: 'online', wait_hours: 24, liveness_raised: false, not_before: '2026-11-26T00:01:00Z', ended_at: null, end_reason: null, source: '203.0.113.9' }];
  const fullWaits = { ...waits, values: { cooling_off_days: 7, contact_wait_hours: 24, remote_wait_hours: 72 }, options: { cooling_off_days: [3, 7, 14], contact_wait_hours: [24, 48, 72], remote_wait_hours: [72, 168] } };
  const calls = gateway((_method, path) => {
    if (path === '/v1/auth/recovery') return Response.json(running);
    if (path === '/v1/auth/recovery/settings') return Response.json(fullWaits);
    if (path === '/v1/auth/recovery/requests/rr_1/cancel') return Response.json({ ...running[0], state: 'cancelled' });
    return Response.json([]);
  });
  render(<RecoveryContacts />);
  expect(await screen.findByText(/from 203.0.113.9/)).toBeVisible();
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText('Wait with no contact'), '168');
  await user.click(screen.getByRole('button', { name: 'Stop recovery rr_1' }));
  expect(calls.some((c) => c.method === 'POST' && c.path === '/v1/auth/recovery/requests/rr_1/cancel')).toBe(true);
  expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ remote_wait_hours: 168 });
});

it('shows an open legacy claim to the owner, who cancels and blocks; an adult confirms as the second person', async () => {
  handlesLegacy = true;
  const claim = { id: 'lcl_1', contact_id: 'rc_9', state: 'waiting', created_at: '2026-11-25T00:00:00Z', ends_at: '2026-12-25T00:00:00Z', needs_second: true, second_confirmed: false, granted_at: null, access_until: null, ended_at: null, end_reason: null, certificate_type: 'application/pdf', contact_display_name: 'Ana' };
  state.role = 'owner';
  let calls = gateway((_method, path) => {
    if (path === '/v1/auth/legacy/claims') return Response.json([claim]);
    if (path === '/v1/auth/recovery/settings') return Response.json(waits);
    if (path.endsWith('/cancel')) return Response.json({ ...claim, state: 'cancelled' });
    return Response.json([]);
  });
  const { unmount } = render(<RecoveryContacts />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Cancel and block lcl_1' }));
  expect(calls.find((c) => c.path === '/v1/auth/legacy/claims/lcl_1/cancel')?.body).toEqual({ block: true });
  unmount();
  state.role = 'adult';
  calls = gateway((_method, path) => (path === '/v1/auth/legacy/claims' ? Response.json([claim]) : path.endsWith('/confirm') ? Response.json(claim) : Response.json([])));
  render(<RecoveryContacts />);
  await user.click(await screen.findByRole('button', { name: 'Confirm claim lcl_1' }));
  expect(calls.some((c) => c.method === 'POST' && c.path === '/v1/auth/legacy/claims/lcl_1/confirm')).toBe(true);
  expect(screen.queryByRole('button', { name: 'Cancel claim lcl_1' })).toBeNull();
});

it('shows who confirmed next to the claimant and flags a claimant who accepted signed out', async () => {
  handlesLegacy = true;
  const claim = { id: 'lcl_2', contact_id: 'rc_9', state: 'awaiting_second', created_at: '2026-11-25T00:00:00Z', ends_at: '2026-12-25T00:00:00Z', needs_second: true, second_confirmed: true, granted_at: null, access_until: null, ended_at: null, end_reason: null, certificate_type: 'application/pdf', contact_display_name: 'Ana', confirmed_by_display_name: 'Ben', claimant_accepted_signed_in: false };
  state.role = 'owner';
  gateway((_method, path) => {
    if (path === '/v1/auth/legacy/claims') return Response.json([claim]);
    if (path === '/v1/auth/recovery/settings') return Response.json(waits);
    return Response.json([]);
  });
  render(<RecoveryContacts />);
  expect(await screen.findByText(/confirmed by Ben/)).toBeTruthy();
  expect(screen.getByText(/accepted on a signed-out phone/)).toBeTruthy();
});

it('lets an owner end a granted export, not only an open claim', async () => {
  handlesLegacy = true;
  const claim = { id: 'lcl_3', contact_id: 'rc_9', state: 'granted', created_at: '2026-11-25T00:00:00Z', ends_at: '2026-12-25T00:00:00Z', needs_second: false, second_confirmed: false, granted_at: '2026-12-25T00:00:00Z', access_until: '2027-12-25T00:00:00Z', ended_at: null, end_reason: null, certificate_type: 'application/pdf', contact_display_name: 'Ana' };
  state.role = 'owner';
  const calls = gateway((_method, path) => {
    if (path === '/v1/auth/legacy/claims') return Response.json([claim]);
    if (path === '/v1/auth/recovery/settings') return Response.json(waits);
    if (path.endsWith('/cancel')) return Response.json({ ...claim, state: 'cancelled' });
    return Response.json([]);
  });
  render(<RecoveryContacts />);
  expect(await screen.findByText(/export open until/)).toBeTruthy();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Cancel claim lcl_3' }));
  expect(calls.find((c) => c.path === '/v1/auth/legacy/claims/lcl_3/cancel')?.body).toEqual({ block: false });
});
