// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '../api/types';
import { keyErrorText } from '../lib/keyErrors';
import { LAST_PROVEN_WARNING, SignInKeys } from './SignInKeys';

const state = vi.hoisted(() => ({ role: 'owner' as string | null | undefined, signOut: vi.fn() }));
vi.mock('../session', () => ({
  useSignedIn: () => ({ token: 'fixture', mock: false, principal: { id: 'zeus', kind: 'person' } }), // a real gateway session has no role on the principal
  useSession: () => ({ signOut: state.signOut }),
}));
vi.mock('../shell/Shell', () => ({ useShell: () => ({ role: state.role }) })); // the role GET /v1/me answered
const webauthn = vi.hoisted(() => ({ create: vi.fn(), get: vi.fn() }));
vi.mock('../lib/webauthn', () => ({
  webauthnSupported: () => true,
  createPasskey: webauthn.create,
  getPasskey: webauthn.get,
}));
const box = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock('../lib/boxcode', () => ({ askBoxCode: box.ask }));
beforeEach(() => { webauthn.create.mockResolvedValue({ id: 'new' }); webauthn.get.mockResolvedValue({ id: 'bio' }); box.ask.mockResolvedValue('482913'); });
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

const phone = { credential_id: 'phone', label: 'iPhone', created_at: '2026-11-20T10:00:00Z', last_used_at: null, level: 'L1',
  level_reason: 'no_attestation', explanation: 'This passkey can’t prove its make and model. It works for everyday approvals.',
  model: null, aaguid: null, attestation: 'none', device_bound: false, synced: true };
const bio = { ...phone, credential_id: 'bio', label: 'Bio key', level: 'L2', level_reason: 'proven', explanation: 'A proven key.',
  model: 'Test Bio Key', attestation: 'packed', device_bound: true, synced: false };
const table = { rows: [], types: [], household_level: 'L1', grace: true, recovery_needed: false, box_confirm: true };

type Call = { method: string; path: string; search: string; body: unknown; headers: Record<string, string> };
function gateway(route: (c: Call) => unknown) {
  const calls: Call[] = [];
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    const { pathname, search } = new URL(url);
    const c = { method: init.method ?? 'GET', path: pathname, search, body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: (init.headers ?? {}) as Record<string, string> };
    calls.push(c);
    const out = route(c);
    if (out === 204) return new Response(null, { status: 204 });
    if (out instanceof Response) return out;
    return out === undefined ? Response.json({ error: 'not_found', message: 'no' }, { status: 404 }) : Response.json(out);
  });
  vi.stubGlobal('fetch', fetch);
  return calls;
}
const mount = () => render(<MemoryRouter><SignInKeys /></MemoryRouter>);

it('starts delayed remote recovery with a kit code and withholds registration until the gateway says ready', async () => {
  let waiting = false;
  const calls = gateway(({ method, path }) => {
    if (path === '/v1/auth/recovery/remote') {
      if (method === 'POST') waiting = true;
      if (method === 'DELETE') { waiting = false; return 204; }
      return { state: waiting ? 'waiting' : 'none', available_at: waiting ? '2026-11-30T12:00:00Z' : null, expires_at: '2026-12-07T12:00:00Z' };
    }
    return ({ '/v1/auth/passkeys': [], '/v1/verification-requirements': table, '/v1/auth/authenticator-allowlist': [] } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Recovery kit code'), 'kit-test-code');
  await user.click(screen.getByRole('button', { name: 'Start the 72-hour wait' }));
  expect(await screen.findByText(/You can register a replacement key after/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Add a replacement proven key' })).toBeNull();
  expect(calls.find((c) => c.method === 'POST' && c.path === '/v1/auth/recovery/remote')?.body).toEqual({ recovery_code: 'kit-test-code' });
  await user.click(screen.getByRole('button', { name: 'Cancel recovery' }));
  expect(await screen.findByLabelText('Recovery kit code')).toHaveValue('');
});

it('uses the dedicated recovery challenge to register a proven key after the wait', async () => {
  let registered = false;
  const calls = gateway(({ path }) => {
    if (path === '/v1/auth/recovery/remote') return { state: registered ? 'none' : 'ready', available_at: '2026-11-30T12:00:00Z', expires_at: '2026-12-07T12:00:00Z' };
    if (path === '/v1/auth/passkeys/register/options') return { publicKey: { challenge: 'remote' } };
    if (path === '/v1/auth/passkeys/register') { registered = true; return { ...bio, label: 'Recovery key' }; }
    return ({ '/v1/auth/passkeys': registered ? [bio] : [], '/v1/verification-requirements': table, '/v1/auth/authenticator-allowlist': [] } as Record<string, unknown>)[path];
  });
  mount();
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Add a replacement proven key' }));
  expect(await screen.findByText('Recovery key added at L2.')).toBeVisible();
  expect(calls.find((c) => c.path === '/v1/auth/passkeys/register/options')?.search).toBe('?remote_recovery=true');
  expect(calls.find((c) => c.path === '/v1/auth/passkeys/register')?.body).toEqual({ credential: { id: 'new' }, label: 'Recovery key' });
  expect(box.ask).not.toHaveBeenCalled();
});

it('shows each key’s level, why a key is only a Device check, and the two-key nudge', async () => {
  gateway(({ path }) => ({ '/v1/auth/passkeys': [phone], '/v1/verification-requirements': table, '/v1/auth/authenticator-allowlist': [] })[path]);
  mount();
  expect(await screen.findByText('L1 · Device check')).toBeVisible();
  expect(screen.getByText(/can’t prove its make and model/)).toBeVisible();
  expect(screen.getByText('Synced between devices')).toBeVisible();
  expect(screen.getByRole('heading', { name: 'Add two proven keys' })).toBeVisible();
  expect(await screen.findByText(/accept a Device check key plus the code on the box's own screen/)).toBeVisible();
  expect(screen.getByText('No trusted models yet, so every key works at Device check.')).toBeVisible();
});

it('says no more once two proven keys exist', async () => {
  gateway(({ path }) => ({ '/v1/auth/passkeys': [bio, { ...bio, credential_id: 'b2', label: 'Spare' }], '/v1/verification-requirements': { ...table, grace: false }, '/v1/auth/authenticator-allowlist': [] })[path]);
  mount();
  expect(await screen.findAllByText('L2 · Proven key')).toHaveLength(2);
  expect(screen.queryByRole('heading', { name: /proven key/ })).toBeNull();
});

it('enrolling a key that can only reach L1 shows the explanation', async () => {
  const calls = gateway(({ method, path }) => {
    if (path === '/v1/auth/passkeys') return method === 'GET' ? [] : undefined;
    if (path === '/v1/auth/passkeys/register/options') return { challenge_id: 'c', expires_at: '2026-11-25T12:00:00Z', publicKey: { challenge: 'x', attestation: 'direct' } };
    if (path === '/v1/auth/passkeys/register') return { credential_id: 'new', label: 'Laptop', created_at: '2026-11-25T12:00:00Z', level: 'L1', level_reason: 'no_attestation', explanation: 'This passkey can’t prove its make and model.' };
    return ({ '/v1/verification-requirements': table, '/v1/auth/authenticator-allowlist': [] } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Name for the new key'), 'Laptop');
  await user.click(screen.getByRole('button', { name: 'Add a key' }));
  expect(await screen.findByText('Laptop added at L1. This passkey can’t prove its make and model.')).toBeVisible();
  expect(calls.find((c) => c.path === '/v1/auth/passkeys/register')?.body).toEqual({ credential: { id: 'new' }, label: 'Laptop' });
});

it('a proven key vouches for a new one with a step-up bound to this change', async () => {
  const calls = gateway(({ method, path, headers }) => {
    if (path === '/v1/auth/passkeys') return method === 'GET' ? [bio] : undefined;
    if (path === '/v1/auth/passkeys/register/options') {
      // The hub names the step-up in details; the SDK's shared helper makes it in place.
      if (headers['OneMind-Step-Up'] !== 'grant-1') return Response.json({ error: 'unauthenticated', message: 'needs L2', reason: 'step_up_required',
        details: [{ step_up: { op: 'auth.passkeys.register', target: '', body: {}, required_level: 'L2' } }] }, { status: 401 });
      return { challenge_id: 'c', expires_at: '2026-11-25T12:00:00Z', publicKey: { challenge: 'x' } };
    }
    if (path === '/v1/auth/step-up/options') return { challenge_id: 's', expires_at: '2026-11-25T12:00:00Z', required_level: 'L2', grace: false, publicKey: { challenge: 'y' } };
    if (path === '/v1/auth/step-up') return { step_up: 'grant-1', expires_at: '2026-11-25T12:02:00Z', level: 'L2' };
    if (path === '/v1/auth/passkeys/register') return { credential_id: 'new', label: 'Security key', created_at: '2026-11-25T12:00:00Z', level: 'L2', level_reason: 'proven', explanation: 'A proven key.' };
    return ({ '/v1/verification-requirements': { ...table, grace: false }, '/v1/auth/authenticator-allowlist': [] } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Add a key' }));
  expect(await screen.findByText('Security key added at L2. A proven key.')).toBeVisible();
  expect(calls.find((c) => c.path === '/v1/auth/step-up/options')?.body).toEqual({ op: 'auth.passkeys.register', target: '', body: {} });
  expect(webauthn.get).toHaveBeenCalledWith({ challenge: 'y' });
});

it('removes a key only after a second click', async () => {
  let removed = false;
  gateway(({ method, path }) => {
    if (method === 'DELETE' && path === '/v1/auth/passkeys/phone') { removed = true; return 204; }
    return ({ '/v1/auth/passkeys': removed ? [bio] : [phone, bio], '/v1/verification-requirements': table, '/v1/auth/authenticator-allowlist': [] } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove iPhone' }));
  expect(removed).toBe(false);
  await user.click(screen.getByRole('button', { name: 'Confirm remove iPhone' }));
  await waitFor(() => expect(removed).toBe(true));
  await waitFor(() => expect(screen.queryByText('iPhone')).toBeNull());
});

it('warns before the last proven key goes, and a removal confirms with a passkey in place', async () => {
  let removed = false;
  const calls = gateway(({ method, path, headers }) => {
    if (method === 'DELETE' && path === '/v1/auth/passkeys/bio') {
      if (headers['OneMind-Step-Up'] !== 'grant-2') return Response.json({ error: 'unauthenticated', message: 'confirm it is you', reason: 'step_up_required',
        details: [{ step_up: { op: 'auth.passkeys.delete', target: 'bio', body: {}, required_level: 'L2', box: 'alt' } }] }, { status: 401 });
      removed = true; return 204;
    }
    if (path === '/v1/auth/step-up/options') return { challenge_id: 's', expires_at: '2026-11-25T12:00:00Z', required_level: 'L2', grace: false, box_code_required: false, publicKey: { challenge: 'z' } };
    if (path === '/v1/auth/step-up') return { step_up: 'grant-2', expires_at: '2026-11-25T12:02:00Z', level: 'L2' };
    return ({ '/v1/auth/passkeys': removed ? [phone] : [phone, bio], '/v1/verification-requirements': { ...table, grace: false }, '/v1/auth/authenticator-allowlist': [] } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove Bio key' }));
  expect(screen.getByRole('alert')).toHaveTextContent(LAST_PROVEN_WARNING);
  // Design 3.11: a recovery path is needed afterwards; nothing goes back to a Device check key.
  expect(LAST_PROVEN_WARNING).toMatch(/need a recovery path until you add another strong key/);
  expect(LAST_PROVEN_WARNING).toMatch(/never go back to accepting a Device check key/);
  await user.click(screen.getByRole('button', { name: 'Confirm remove Bio key' }));
  await waitFor(() => expect(removed).toBe(true));
  expect(calls.find((c) => c.path === '/v1/auth/step-up/options')?.body).toEqual({ op: 'auth.passkeys.delete', target: 'bio', body: {} });
  expect(box.ask).not.toHaveBeenCalled(); // the key confirms its own removal: no box code
  // A Device check key is not the last proven key: no warning for it.
  await user.click(await screen.findByRole('button', { name: 'Remove iPhone' }));
  expect(screen.queryByRole('alert')).toBeNull();
});

it('a lost last proven key is removed by confirming at the box', async () => {
  let removed = false;
  const calls = gateway(({ method, path, headers }) => {
    if (method === 'DELETE' && path === '/v1/auth/passkeys/bio') { removed = headers['OneMind-Step-Up'] === 'grant-3'; return removed ? 204 : undefined; }
    if (path === '/v1/auth/step-up/options') return { challenge_id: 's', expires_at: '2026-11-25T12:00:00Z', required_level: 'L1', grace: false, box_code_required: true, publicKey: { challenge: 'b' } };
    if (path === '/v1/auth/step-up') return { step_up: 'grant-3', expires_at: '2026-11-25T12:02:00Z', level: 'L1' };
    return ({ '/v1/auth/passkeys': removed ? [phone] : [phone, bio], '/v1/verification-requirements': { ...table, grace: false }, '/v1/auth/authenticator-allowlist': [] } as Record<string, unknown>)[path];
  });
  webauthn.get.mockResolvedValue({ id: 'phone' });
  mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove Bio key' }));
  await user.click(screen.getByRole('button', { name: 'Lost Bio key: confirm at the box' }));
  await waitFor(() => expect(removed).toBe(true));
  expect(calls.find((c) => c.path === '/v1/auth/step-up/options')?.body).toEqual({ op: 'auth.passkeys.delete', target: 'bio', body: {}, at_box: true });
  expect(calls.find((c) => c.path === '/v1/auth/step-up')?.body).toEqual({ credential: { id: 'phone' }, box_code: '482913' });
});

it('the box\'s first proven key is added at the box: the page asks for the code and uses the key once more', async () => {
  let tries = 0;
  const calls = gateway(({ method, path }) => {
    if (path === '/v1/auth/passkeys') return method === 'GET' ? [phone] : undefined;
    if (path === '/v1/auth/passkeys/register/options') return { challenge_id: 'c', expires_at: '2026-11-25T12:00:00Z', publicKey: { challenge: 'x' }, box_code_if_proven: true };
    if (path === '/v1/auth/passkeys/register') {
      tries += 1;
      if (tries === 1) return Response.json({ error: 'unauthenticated', message: 'type the code', reason: 'box_code_required' }, { status: 401 });
      return { credential_id: 'new', label: 'Security key', created_at: '2026-11-25T12:00:00Z', level: 'L2', level_reason: 'proven', explanation: 'A proven key.' };
    }
    return ({ '/v1/verification-requirements': table, '/v1/auth/authenticator-allowlist': [] } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Add a key' }));
  expect(await screen.findByText('Security key added at L2. A proven key.')).toBeVisible();
  const sent = calls.filter((c) => c.path === '/v1/auth/passkeys/register').map((c) => c.body);
  expect(sent).toEqual([{ credential: { id: 'new' }, label: 'Security key' }, { credential: { id: 'new' }, label: 'Security key', box_code: '482913' }]);
  expect(box.ask).toHaveBeenCalledExactlyOnceWith('add a proven key');
});

it('after the last proven key is gone the nudge says approvals wait, not that a Device check key works', async () => {
  gateway(({ path }) => ({ '/v1/auth/passkeys': [phone], '/v1/verification-requirements': { ...table, grace: false, recovery_needed: true }, '/v1/auth/authenticator-allowlist': [] })[path]);
  mount();
  expect(await screen.findByText(/had a proven key and has none now/)).toBeVisible();
  expect(screen.queryByText(/accept a Device check key/)).toBeNull();
});

it('says what to do when a passkey check could not be made, instead of "try again"', () => {
  expect(keyErrorText(new ApiError(401, 'unauthenticated', 'sign in again', 'step_up_required'))).toMatch(/sign in again with your passkey/);
  expect(keyErrorText(Object.assign(new Error('x'), { name: 'NotAllowedError' }))).toMatch(/cancelled .* nothing changed/);
  expect(keyErrorText(new ApiError(409, 'conflict', 'x', 'verification_level_unmet'))).toMatch(/proven key/);
  expect(keyErrorText(new ApiError(401, 'unauthenticated', 'x', 'box_code_required'))).toMatch(/box's own screen .* new code/);
  expect(keyErrorText(new ApiError(429, 'rate_limited', 'x', 'box_code_locked'))).toMatch(/15 minutes/);
});

it('an owner asks to trust a key model through Approvals and can stop trusting one', async () => {
  const model = { aaguid: 'a1b2c3d4-0000-4000-8000-00000000b10e', name: 'Test Bio Key', user_verification: ['fingerprint_internal'], biometric: true, roots: 1, source: 'owner', added_at: null };
  let untrusted = false;
  const calls = gateway(({ method, path }) => {
    if (method === 'POST' && path === '/v1/actions') return { id: 'act-5', state: 'awaiting_approval' };
    if (method === 'DELETE' && path.startsWith('/v1/auth/authenticator-allowlist/')) { untrusted = true; return 204; }
    return ({ '/v1/auth/passkeys': [phone], '/v1/verification-requirements': table, '/v1/auth/authenticator-allowlist': untrusted ? [] : [model] } as Record<string, unknown>)[path];
  });
  mount();
  const user = userEvent.setup();
  expect(await screen.findByText('Test Bio Key')).toBeVisible();
  await user.click(screen.getByText('Trust another model'));
  await user.type(screen.getByLabelText('Model id (AAGUID)'), 'a1b2c3d4000040008000000000000b1f');
  await user.type(screen.getByLabelText('Model name'), 'Other Key');
  await user.type(screen.getByLabelText('Attestation root certificate (PEM)'), '-----BEGIN CERTIFICATE-----MIIB-----END CERTIFICATE-----');
  await user.click(screen.getByRole('button', { name: 'Ask to trust this model' }));
  expect(await screen.findByText(/Approve it in Approvals with your proven key/)).toBeVisible();
  const filed = calls.find((c) => c.method === 'POST' && c.path === '/v1/actions')?.body as { type: string; params: Record<string, unknown> };
  expect(filed.type).toBe('authenticator.allowlist.add');
  expect(filed.params).toMatchObject({ name: 'Other Key', user_verification: ['fingerprint_internal'] });
  await user.click(screen.getByRole('button', { name: 'Stop trusting Test Bio Key' }));
  expect(untrusted).toBe(false); // a confirm step first, naming the keys that drop
  expect(screen.getByText('None of your keys is of this model.')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Confirm stop trusting Test Bio Key' }));
  await waitFor(() => expect(untrusted).toBe(true));
});

it('an adult manages their own keys and never sees the owner’s trusted models', async () => {
  state.role = 'adult';
  try {
    const calls = gateway(({ path }) => ({ '/v1/auth/passkeys': [phone] } as Record<string, unknown>)[path]);
    mount();
    expect(await screen.findByText('L1 · Device check')).toBeVisible();
    expect(screen.queryByText('Trusted key models')).toBeNull();
    expect(calls.every((c) => c.path === '/v1/auth/passkeys')).toBe(true);
  } finally { state.role = 'owner'; }
});

it('hides the owner’s trusted models until GET /v1/me has named the role (fail closed)', async () => {
  state.role = undefined;
  try {
    const calls = gateway(({ path }) => ({ '/v1/auth/passkeys': [phone] } as Record<string, unknown>)[path]);
    mount();
    expect(await screen.findByText('L1 · Device check')).toBeVisible();
    expect(screen.queryByText('Trusted key models')).toBeNull();
    expect(calls.every((c) => c.path === '/v1/auth/passkeys')).toBe(true);
  } finally { state.role = 'owner'; }
});

it('shows nothing owner-only for an agent (role null)', async () => {
  state.role = null;
  try {
    const calls = gateway(({ path }) => ({ '/v1/auth/passkeys': [phone] } as Record<string, unknown>)[path]);
    mount();
    expect(await screen.findByText('L1 · Device check')).toBeVisible();
    expect(screen.queryByText('Trusted key models')).toBeNull();
    expect(calls.every((c) => c.path === '/v1/auth/passkeys')).toBe(true);
  } finally { state.role = 'owner'; }
});
