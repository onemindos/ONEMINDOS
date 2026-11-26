// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SignInKeys } from './SignInKeys';

const state = vi.hoisted(() => ({ role: 'owner', signOut: vi.fn() }));
vi.mock('../session', () => ({
  useSignedIn: () => ({ token: 'fixture', mock: false, principal: { id: 'zeus', kind: 'person', role: state.role } }),
  useSession: () => ({ signOut: state.signOut }),
}));
const webauthn = vi.hoisted(() => ({ create: vi.fn(), get: vi.fn() }));
vi.mock('../lib/webauthn', () => ({
  webauthnSupported: () => true,
  createPasskey: webauthn.create,
  getPasskey: webauthn.get,
}));
beforeEach(() => { webauthn.create.mockResolvedValue({ id: 'new' }); webauthn.get.mockResolvedValue({ id: 'bio' }); });
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

const phone = { credential_id: 'phone', label: 'iPhone', created_at: '2026-11-20T10:00:00Z', last_used_at: null, level: 'L1',
  level_reason: 'no_attestation', explanation: 'This passkey can’t prove its make and model. It works for everyday approvals.',
  model: null, aaguid: null, attestation: 'none', device_bound: false, synced: true };
const bio = { ...phone, credential_id: 'bio', label: 'Bio key', level: 'L2', level_reason: 'proven', explanation: 'A proven key.',
  model: 'Test Bio Key', attestation: 'packed', device_bound: true, synced: false };
const table = { rows: [], types: [], household_level: 'L1', grace: true };

type Call = { method: string; path: string; body: unknown; headers: Record<string, string> };
function gateway(route: (c: Call) => unknown) {
  const calls: Call[] = [];
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    const c = { method: init.method ?? 'GET', path: new URL(url).pathname, body: init.body ? JSON.parse(String(init.body)) : undefined,
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

it('shows each key’s level, why a key is only a Device check, and the two-key nudge', async () => {
  gateway(({ path }) => ({ '/v1/auth/passkeys': [phone], '/v1/verification-requirements': table, '/v1/auth/authenticator-allowlist': [] })[path]);
  mount();
  expect(await screen.findByText('L1 · Device check')).toBeVisible();
  expect(screen.getByText(/can’t prove its make and model/)).toBeVisible();
  expect(screen.getByText('Synced between devices')).toBeVisible();
  expect(screen.getByRole('heading', { name: 'Add two proven keys' })).toBeVisible();
  expect(await screen.findByText(/accept a Device check key/)).toBeVisible();
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
      if (headers['OneMind-Step-Up'] !== 'grant-1') return Response.json({ error: 'unauthenticated', message: 'needs L2', reason: 'step_up_required' }, { status: 401 });
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
