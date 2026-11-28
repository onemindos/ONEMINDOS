// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { AccountSignIn } from './AccountSignIn';

const state = vi.hoisted(() => ({ mock: false }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture', mock: state.mock }), useSession: () => ({ signOut: vi.fn() }) }));
afterEach(() => { vi.unstubAllGlobals(); state.mock = false; });

type Methods = { password: boolean; totp: boolean; passkeys: number; passkeys_active: boolean };
type Call = { method: string; path: string; body?: unknown };

// A gateway with the routes of core/onemind_core/routers/identity.py that this screen calls.
function gateway(start: Methods, answer: (c: Call) => Response | undefined = () => undefined) {
  const methods = { ...start };
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const c: Call = { method: init?.method ?? 'GET', path: new URL(url).pathname, body: init?.body ? JSON.parse(String(init.body)) : undefined };
    calls.push(c);
    const custom = answer(c);
    if (custom) return custom;
    if (c.path === '/v1/auth/methods') return Response.json(methods);
    if (c.path === '/v1/auth/totp/setup') return Response.json({ one_time: { secret: 'JBSWY3DPEHPK3PXP', otpauth_uri: 'otpauth://totp/OneMind:zeus?secret=JBSWY3DPEHPK3PXP' } });
    if (c.path === '/v1/auth/totp/confirm') { methods.totp = true; return new Response(null, { status: 204 }); }
    if (c.path === '/v1/auth/totp/disable') { methods.totp = false; return new Response(null, { status: 204 }); }
    if (c.path === '/v1/auth/password') return new Response(null, { status: 204 });
    return Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  }));
  return calls;
}

it('puts passkeys first: a passkey user is not asked to add an authenticator code', async () => {
  gateway({ password: true, totp: false, passkeys: 1, passkeys_active: true });
  render(<AccountSignIn />);
  const card = (await screen.findByRole('heading', { name: 'Authenticator code' })).closest('section')!;
  expect(within(card).getByText(/Passkeys are recommended/)).toBeInTheDocument();
  expect(within(card).getByText('Off')).toBeInTheDocument();
  // The set-up button sits inside a closed disclosure, never as the card's call to action.
  expect(within(card).getByText(/you do not need this/).closest('details')).not.toHaveAttribute('open');
  expect(screen.getByRole('heading', { name: 'Password' })).toBeInTheDocument();
});

it('changes the password only when the two new ones match, and says what happened', async () => {
  const calls = gateway({ password: true, totp: false, passkeys: 0, passkeys_active: false });
  const user = userEvent.setup();
  render(<AccountSignIn />);
  const change = await screen.findByRole('button', { name: 'Change password' });
  await user.type(screen.getByLabelText('Current password'), 'old password 1');
  await user.type(screen.getByLabelText('New password'), 'new password 22');
  await user.type(screen.getByLabelText('New password again'), 'new password 2');
  expect(screen.getByText('The two new passwords are not the same.')).toBeInTheDocument();
  expect(change).toBeDisabled();
  await user.type(screen.getByLabelText('New password again'), '2');
  await user.click(change);
  expect(await screen.findByText(/Your password is changed/)).toBeInTheDocument();
  expect(calls.filter((c) => c.method === 'POST')).toEqual([{ method: 'POST', path: '/v1/auth/password', body: { current_password: 'old password 1', new_password: 'new password 22' } }]);
  expect(screen.getByLabelText('Current password')).toHaveValue('');
});

it('says in plain words when the current password is wrong', async () => {
  gateway({ password: true, totp: false, passkeys: 0, passkeys_active: false }, (c) =>
    c.path === '/v1/auth/password' ? Response.json({ error: 'unauthenticated', message: 'current password is wrong', reason: 'bad_credentials' }, { status: 401 }) : undefined);
  const user = userEvent.setup();
  render(<AccountSignIn />);
  await user.type(await screen.findByLabelText('Current password'), 'nope');
  await user.type(screen.getByLabelText('New password'), 'new password 22');
  await user.type(screen.getByLabelText('New password again'), 'new password 22');
  await user.click(screen.getByRole('button', { name: 'Change password' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('That password is not right. Nothing was changed.');
});

async function changePassword() {
  const user = userEvent.setup();
  render(<AccountSignIn />);
  await user.type(await screen.findByLabelText('Current password'), 'old password 1');
  await user.type(screen.getByLabelText('New password'), 'new password 22');
  await user.type(screen.getByLabelText('New password again'), 'new password 22');
  await user.click(screen.getByRole('button', { name: 'Change password' }));
}

it('says to sign in when the gateway refuses an API token (the real 403 body)', async () => {
  // IdentityService._account -> deny(..., tell=True): the body core test_identity asserts.
  gateway({ password: true, totp: false, passkeys: 0, passkeys_active: false }, (c) =>
    c.path === '/v1/auth/password' ? Response.json({ error: 'permission_denied', message: 'not allowed to change the password', reason: 'session_required' }, { status: 403 }) : undefined);
  await changePassword();
  expect(await screen.findByRole('alert')).toHaveTextContent('This needs you to be signed in on this device.');
});

it('says nothing was changed when the box does not answer', async () => {
  gateway({ password: true, totp: false, passkeys: 0, passkeys_active: false });
  const answered = globalThis.fetch;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (new URL(url).pathname === '/v1/auth/password') throw new TypeError('Failed to fetch');
    return answered(url, init);
  }));
  await changePassword();
  expect(await screen.findByRole('alert', {}, { timeout: 5000 })).toHaveTextContent('The box did not answer. Nothing was changed; try again.');
});

it('sets up an authenticator code: shows the key once, then turns it on with a code', async () => {
  const calls = gateway({ password: true, totp: false, passkeys: 0, passkeys_active: false });
  const user = userEvent.setup();
  render(<AccountSignIn />);
  expect(await screen.findByText(/The safer step is a passkey/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Set up an authenticator code' }));
  expect(await screen.findByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'QR code for your authenticator app' })).toBeInTheDocument();
  const on = screen.getByRole('button', { name: 'Turn on' });
  await user.type(screen.getByLabelText('The 6-digit code your app shows'), '12a3456');
  expect(screen.getByLabelText('The 6-digit code your app shows')).toHaveValue('123456');
  await user.click(on);
  expect(await screen.findByText(/The authenticator code is on/)).toBeInTheDocument();
  expect(await screen.findByText('On')).toBeInTheDocument();
  expect(screen.queryByText('JBSWY3DPEHPK3PXP')).toBeNull();
  expect(calls.find((c) => c.path === '/v1/auth/totp/confirm')?.body).toEqual({ code: '123456' });
});

it('turns the authenticator code off only with the password', async () => {
  const calls = gateway({ password: true, totp: true, passkeys: 1, passkeys_active: true });
  const user = userEvent.setup();
  render(<AccountSignIn />);
  await user.click(await screen.findByRole('button', { name: 'Turn off the authenticator code' }));
  const off = screen.getByRole('button', { name: 'Turn off' });
  expect(off).toBeDisabled();
  await user.type(screen.getByLabelText('Your password'), 'my password 1');
  await user.click(off);
  expect(await screen.findByText('The authenticator code is off.')).toBeInTheDocument();
  expect(calls.find((c) => c.path === '/v1/auth/totp/disable')?.body).toEqual({ password: 'my password 1' });
});

it('offers nothing to a person without a password', async () => {
  gateway({ password: false, totp: false, passkeys: 2, passkeys_active: true });
  render(<AccountSignIn />);
  expect(await screen.findByText(/There is nothing to set up/)).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Password' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Set up an authenticator code' })).toBeNull();
});

it('calls nothing in demo mode', async () => {
  state.mock = true;
  const calls = gateway({ password: true, totp: false, passkeys: 0, passkeys_active: false });
  render(<AccountSignIn />);
  expect(screen.getByText(/Demo mode has no real account/)).toBeInTheDocument();
  expect(calls).toEqual([]);
});
