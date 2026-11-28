// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { BoxCodeHost } from '../lib/boxcode';
import * as webauthn from '../lib/webauthn';
import { SessionProvider } from '../session';
import { IdentityFactors } from './IdentityFactors';

type Route = (method: string, path: string, body: unknown, headers: Headers) => Response | undefined;
const challenge = { challenge_id: 'screen-challenge', expires_at: '2030-01-01T00:02:00Z' };
const json = (value: unknown, status = 200) => Response.json(value, { status });

function mount(route: Route, pending: () => boolean = () => false) {
  const deps = {
    mock: false,
    knownPrincipal: (token: string) => DEMO_TOKENS[token],
    makeApi(token: string) {
      const http = new HttpApi({ token, fetchFn: async (url, init) => {
        const answer = route(init?.method ?? 'GET', new URL(url, window.location.origin).pathname,
          init?.body ? JSON.parse(String(init.body)) : undefined, new Headers(init?.headers));
        return answer ?? json({ error: 'not_found', message: 'No handler in this test.' }, 404);
      } });
      const client = new MockApi(token);
      const me = client.me.bind(client);
      return Object.assign(client, {
        setupStatus: http.setupStatus, setupOptions: http.setupOptions, setupAtBox: http.setupAtBox,
        setupKit: http.setupKit, finishSetup: http.finishSetup, recoveryOptions: http.recoveryOptions,
        resetPasswordAtBox: http.resetPasswordAtBox, loginPassword: http.loginPassword.bind(http), enrol: http.enrol.bind(http),
        updateIdentityEmail: http.updateIdentityEmail, emailOptions: http.emailOptions, verifyIdentityEmail: http.verifyIdentityEmail,
        setupTotp: http.setupTotp, confirmTotp: http.confirmTotp, disableTotp: http.disableTotp,
        me: async () => ({ ...await me(), setup_pending: pending() }),
      });
    },
  };
  return render(<MemoryRouter><SessionProvider deps={deps}><App mock={false} /></SessionProvider></MemoryRouter>);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});

it('uses the screen during first run and waits for a file download and explicit kit confirmation', async () => {
  let pending = false;
  const call = vi.fn<Route>((method, path) => {
    if (path === '/v1/auth/setup/status') return json({ state: 'unclaimed', screen: true });
    if (path === '/v1/auth/setup/options') return json(challenge);
    if (path === '/v1/auth/setup') { pending = true; return json({ access_token: 'owner-demo' }, 201); }
    if (method === 'POST' && path === '/v1/auth/setup/kit') return json({ recovery_code: 'test-kit-code', disk_recovery_key: 'test-disk-key' });
    if (path === '/v1/auth/setup/finish') { pending = false; return new Response(null, { status: 204 }); }
  });
  const download = vi.fn();
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = download.mockReturnValue('blob:https://box.local/test');
    static revokeObjectURL = vi.fn();
  });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  mount(call, () => pending);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: /first time on this box/i }));
  await user.click(screen.getByRole('button', { name: 'Show a code on the box' }));
  expect(screen.queryByLabelText('Your name')).toBeNull();
  await user.type(await screen.findByLabelText(/Code on the box/), '012345');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.type(screen.getByLabelText('Your name'), 'Bea Example');
  await user.click(screen.getByLabelText(/^Password/));
  await user.paste('a long passphrase');
  await user.click(screen.getByRole('button', { name: 'Create the owner' }));
  expect(await screen.findByRole('heading', { name: 'Finish setting up your account' })).toBeVisible();
  expect(call.mock.calls.find(([, path]) => path === '/v1/auth/setup')?.[2]).toEqual({
    challenge_id: 'screen-challenge', box_code: '012345', username: 'bea-example', display_name: 'Bea Example', password: 'a long passphrase', client: 'app',
  });
  // The optional steps can all be skipped.
  await user.click(screen.getByRole('button', { name: 'Continue to recovery kit' }));
  expect(await screen.findByText('test-disk-key')).toBeVisible();
  const confirm = screen.getByRole('checkbox', { name: 'I saved the recovery kit somewhere safe' });
  const finish = screen.getByRole('button', { name: 'Finish' });
  expect(confirm).toBeDisabled();
  expect(finish).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Download kit' }));
  expect(download).toHaveBeenCalledWith(expect.any(Blob));
  expect(click.mock.instances[0]).toHaveProperty('download', 'onemind-recovery-kit.txt');
  expect(finish).toBeDisabled();
  await user.click(confirm);
  await user.click(finish);
  await waitFor(() => expect(call.mock.calls.find(([, path]) => path === '/v1/auth/setup/finish')?.[2]).toEqual({
    saved: true, method: 'download', recovery_code: 'test-kit-code',
  }));
  expect(call.mock.calls.find(([, path]) => path === '/v1/auth/setup/kit')?.[3].get('Authorization')).toBe('Bearer owner-demo');
  expect(JSON.stringify({ ...window.sessionStorage, ...window.localStorage })).not.toContain('test-kit-code');
});

it('confirms a saved encrypted recovery kit after a reboot clears the handoff', async () => {
  let pending = true;
  const call = vi.fn<Route>((method, path, body) => {
    if (path === '/v1/auth/setup/status') return json({ state: 'pending', screen: true });
    if (path === '/v1/auth/setup/kit') return json({
      error: 'unavailable', reason: 'disk_recovery_key_missing', message: 'The disk key handoff was lost.',
    }, 503);
    if (method === 'POST' && path === '/v1/auth/setup/finish') {
      expect(body).toEqual({ saved: true, method: 'print', recovery_code: 'saved-account-code', disk_recovery_key: 'saved-disk-key' });
      pending = false;
      return new Response(null, { status: 204 });
    }
  });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  mount(call, () => pending);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Continue to recovery kit' }));
  const confirm = await screen.findByRole('button', { name: 'Confirm saved kit' });
  expect(confirm).toBeDisabled();
  await user.type(screen.getByLabelText('Recovery code'), 'saved-account-code');
  await user.type(screen.getByLabelText('Disk recovery key'), 'saved-disk-key');
  await user.selectOptions(screen.getByLabelText('How did you save the kit?'), 'print');
  await user.click(confirm);
  await waitFor(() => expect(pending).toBe(false));
  expect(JSON.stringify({ ...window.sessionStorage, ...window.localStorage })).not.toContain('saved-disk-key');
});

it('puts the password form first and explains the outside-network factor requirement', async () => {
  const submit = vi.fn<Route>((_method, path) => {
    if (path === '/v1/auth/setup/status') return json({ state: 'ready', screen: true });
    if (path === '/v1/auth/login') return json({ error: 'unauthenticated', reason: 'remote_factor_required', message: 'Away from home, use an authenticator or passkey.' }, 401);
  });
  mount(submit);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Username'), 'bea');
  await user.type(screen.getByLabelText('Password'), 'a long passphrase');
  await user.click(screen.getByRole('button', { name: 'Log in' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Away from home, use an authenticator or passkey.');
  expect(submit.mock.calls.find(([, path]) => path === '/v1/auth/login')?.[2]).toMatchObject({ username: 'bea', password: 'a long passphrase' });
});

it('resets a password with both codes and lets the owner print the replacement recovery code', async () => {
  const call = vi.fn<Route>((_method, path) => {
    if (path === '/v1/auth/setup/status') return json({ state: 'ready', screen: true });
    if (path === '/v1/auth/recovery/options') return json(challenge);
    if (path === '/v1/auth/recovery/reset') return json({ recovery_code: 'replacement-test-code' });
  });
  const print = vi.spyOn(window, 'print').mockImplementation(() => undefined);
  mount(call);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Forgot your password?' }));
  await user.type(screen.getByLabelText('Username'), 'bea');
  await user.click(screen.getByRole('button', { name: 'Show a code on the box' }));
  await user.type(await screen.findByLabelText(/Code on the box/), '012345');
  expect(screen.getByRole('button', { name: 'Reset password' })).toBeDisabled();
  await user.type(screen.getByLabelText('Recovery code'), 'saved-test-code');
  await user.type(screen.getByLabelText(/^Password/), 'replacement passphrase');
  await user.click(screen.getByRole('button', { name: 'Reset password' }));
  const main = await screen.findByRole('main');
  expect(await within(main).findByText('replacement-test-code')).toBeVisible();
  expect(call.mock.calls.find(([, path]) => path === '/v1/auth/recovery/reset')?.[2]).toEqual({
    challenge_id: 'screen-challenge', box_code: '012345', recovery_code: 'saved-test-code', new_password: 'replacement passphrase',
  });
  await user.click(screen.getByRole('button', { name: 'Print kit' }));
  expect(print).toHaveBeenCalledOnce();
  await user.click(screen.getByRole('checkbox', { name: 'I saved the recovery kit somewhere safe' }));
  await user.click(screen.getByRole('button', { name: 'Finish' }));
  expect(screen.queryByText('replacement-test-code')).toBeNull();
});

it('accepts an invite link and offers optional authenticator enrolment for the new account', async () => {
  window.history.replaceState(null, '', '/#enrol=invite-test-code');
  const call = vi.fn<Route>((_method, path) => {
    if (path === '/v1/auth/setup/status') return json({ state: 'ready', screen: true });
    if (path === '/v1/auth/enrol') return json({ access_token: 'adult-demo' }, 201);
    if (path === '/v1/auth/totp/setup') return json({ one_time: { secret: 'test-key', otpauth_uri: 'otpauth://totp/Test' } });
    if (path === '/v1/auth/totp/confirm') return new Response(null, { status: 204 });
  });
  mount(call);
  const user = userEvent.setup();
  expect(await screen.findByLabelText('Invite code')).toHaveValue('invite-test-code');
  expect(window.location.hash).toBe('');
  await user.type(screen.getByLabelText('Username'), 'bea');
  await user.type(screen.getByLabelText(/^Password/), 'a long passphrase');
  await user.click(screen.getByRole('button', { name: 'Join' }));
  expect(await screen.findByRole('heading', { name: 'Set up your sign-in methods' })).toBeVisible();
  expect(call.mock.calls.find(([, path]) => path === '/v1/auth/enrol')?.[2]).toMatchObject({ code: 'invite-test-code', username: 'bea', password: 'a long passphrase' });
  await user.click(screen.getByRole('button', { name: 'Add an authenticator app' }));
  expect(await screen.findByRole('img', { name: 'Authenticator setup QR code' })).toBeVisible();
  await user.type(screen.getByLabelText('Six-digit authenticator code'), '012345');
  await user.click(screen.getByRole('button', { name: 'Enable authenticator' }));
  expect(await screen.findByText('Authenticator enabled.')).toBeVisible();
  expect(call.mock.calls.find(([, path]) => path === '/v1/auth/totp/confirm')?.[2]).toEqual({ code: '012345' });
  expect(screen.getByRole('button', { name: 'Go to your dashboard' })).toBeEnabled();
});

it('leaves email optional when SMTP is unavailable and verifies it only with the returned challenge and email code', async () => {
  const email = ['owner', 'example.test'].join('@');
  let smtpReady = false;
  const fetchRequest = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === '/v1/auth/email/options') return smtpReady ? json(challenge)
      : json({ error: 'conflict', reason: 'smtp_unavailable', message: 'Configure your own SMTP server to send email.' }, 409);
    if (path === '/v1/auth/email/verify' && init?.method === 'POST') return new Response(null, { status: 204 });
    return json({});
  });
  const api = new HttpApi({ token: 'owner-demo', fetchFn: fetchRequest });
  render(<IdentityFactors api={api} offerEmail email={email} />);
  const user = userEvent.setup();
  expect(screen.getByText(`${email} (unverified)`)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Send verification code' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Configure your own SMTP server to send email.');
  expect(screen.queryByLabelText('Code from your email')).toBeNull();
  expect(screen.getByRole('button', { name: 'Add an authenticator app' })).toBeEnabled();
  smtpReady = true;
  await user.click(screen.getByRole('button', { name: 'Send verification code' }));
  await user.type(await screen.findByLabelText('Code from your email'), '012345');
  await user.click(screen.getByRole('button', { name: 'Verify email address' }));
  expect(await screen.findByText('Email address verified.')).toBeVisible();
  const verify = fetchRequest.mock.calls.find(([url]) => new URL(url).pathname === '/v1/auth/email/verify');
  expect(JSON.parse(String(verify?.[1]?.body))).toEqual({ challenge_id: 'screen-challenge', code: '012345' });
});

it('enrols an everyday passkey directly and tries a proven key again with fresh options and the screen code', async () => {
  vi.spyOn(webauthn, 'webauthnSupported').mockReturnValue(true);
  const ceremony = vi.spyOn(webauthn, 'createPasskey').mockImplementation(async ({ challenge }) => ({ id: challenge }));
  let options = 0;
  const submitted: unknown[] = [];
  const api = new HttpApi({ token: 'owner-demo', fetchFn: async (url, init) => {
    const path = new URL(url).pathname;
    if (path === '/v1/auth/passkeys/register/options') {
      const id = `passkey-${++options}`;
      return json({ ...challenge, challenge_id: id, publicKey: { challenge: id }, box_code_if_proven: true });
    }
    if (path === '/v1/auth/passkeys/register') {
      const body = JSON.parse(String(init?.body));
      submitted.push(body);
      if (body.credential.id === 'passkey-2') return json({ error: 'unauthenticated', reason: 'box_code_required', message: 'Use the code on the box.' }, 401);
      return json({ credential_id: body.credential.id, level: body.box_code ? 'L2' : 'L1' }, 201);
    }
    return json({ error: 'not_found', message: 'Not found.' }, 404);
  } });
  const { rerender } = render(<><IdentityFactors key="everyday" api={api} offerPasskey /><BoxCodeHost /></>);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Add a passkey' }));
  expect(await screen.findByText('Passkey added.')).toBeVisible();
  expect(screen.queryByRole('alertdialog')).toBeNull();
  expect(submitted).toEqual([{ credential: { id: 'passkey-1' } }]);

  rerender(<><IdentityFactors key="proven" api={api} offerPasskey /><BoxCodeHost /></>);
  await user.click(screen.getByRole('button', { name: 'Add a passkey' }));
  const dialog = within(await screen.findByRole('alertdialog', { name: 'Confirm at the box' }));
  expect(options).toBe(3);
  expect(ceremony).toHaveBeenCalledTimes(2);
  await user.type(dialog.getByLabelText("Code on the box's screen"), '482913');
  await user.click(dialog.getByRole('button', { name: 'Continue' }));
  expect(await screen.findByText('Passkey added.')).toBeVisible();
  expect(ceremony.mock.calls).toEqual(['passkey-1', 'passkey-2', 'passkey-3'].map((id) => [{ challenge: id }]));
  expect(submitted).toEqual([
    { credential: { id: 'passkey-1' } },
    { credential: { id: 'passkey-2' } },
    { credential: { id: 'passkey-3' }, box_code: '482913' },
  ]);
});
