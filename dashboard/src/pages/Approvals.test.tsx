// SPDX-License-Identifier: Apache-2.0
// The approval loop (contract §12.4): plan in plain words, passkey step-up bound to the plan hash,
// and the sealed install-secrets form. A stub gateway records exactly what the page sends.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { ApiError, type Action, type ApproveBody } from '../api/types';
import { toActionPlan } from '../data/adapters';
import { approveWithStepUp } from '../lib/approve';
import { SessionProvider } from '../session';

vi.mock('../lib/webauthn', async (orig) => ({
  ...(await orig<typeof import('../lib/webauthn')>()),
  webauthnSupported: () => true,
  getPasskey: vi.fn(async () => ({ id: 'cred-1', type: 'public-key' })),
}));

const T = { timeout: 4000 };
const PLAN = { summary: 'Install Ollama.', objects: [], images: [], volumes: [{ kind: 'PersistentVolumeClaim', effect: 'kept' }], nodes: [], warnings: ['Opens a network path: a to b', 'Needs 8 GB of memory.'], network_paths: [{ from: 'ollama', to: 'open-webui', port: 11434, requirement: 'ollama' }] };
const SHA = 'sha256:plan-one';
const future = () => new Date(Date.now() + 3600_000).toISOString();

function setup(opts: { passkey?: boolean; secrets?: boolean; serverSha?: string; hold?: { plan: boolean; stepUp?: boolean }; levelUnmet?: boolean; level?: Action['required_level'] } = {}) {
  const calls: Array<{ id: string; body?: ApproveBody }> = [];
  const options: string[] = [];
  const api = new MockApi('owner-demo');
  const action: Action = { id: 'act-plan', type: 'app.install', params: { app_id: 'ollama' }, idempotency_key: 'k', expires_at: future(), state: 'awaiting_approval', plan: PLAN, plan_sha256: SHA, requested_by: { id: 'ops-agent', kind: 'agent', role: 'agent' }, created_at: new Date().toISOString() };
  if (opts.hold) {
    action.approval = { hold: true, hold_ms: 2000, physical: false } as Action['approval'];
    if (!opts.hold.plan) { action.plan = null; action.plan_sha256 = undefined; action.params = {}; action.type = 'machine.delete'; }
  }
  if (opts.level) action.required_level = opts.level;
  Object.assign(api, {
    actions: async () => [action],
    action: async () => action,
    me: async () => ({ principal: { id: 'owner', kind: 'person', role: 'owner' }, token: null, session: null, passkeys: opts.passkey ? 1 : 0, scopes: [], capabilities: [], step_up: { passkeys_active: !!opts.passkey, require_passkey_approval: false } }),
    approveOptions: async (id: string) => { options.push(id); if (opts.levelUnmet) throw new ApiError(409, 'conflict', 'this needs your proven key (L2); add one under Settings > Security > Sign-in keys', 'verification_level_unmet'); return { challenge: 'c', action_sha256: 'a', plan_sha256: opts.hold && !opts.hold.plan ? undefined : (opts.serverSha ?? SHA), expires_at: future(), publicKey: { challenge: 'c' } }; },
    approve: async (id: string, body?: ApproveBody) => {
      if (opts.hold?.stepUp && !body?.webauthn) { calls.push({ id, body }); throw new ApiError(401, 'unauthenticated', 'passkey needed', 'step_up_required'); }
      calls.push({ id, body }); return { ...action, state: 'accepted' as const }; },
    appSecrets: async () => ({ app_id: 'ollama', key_id: 'k1', missing_required: opts.secrets ? ['ollama-auth/API_KEY'] : [], secrets: opts.secrets ? [{ name: 'ollama-auth', description: 'Auth', keys: [{ key: 'API_KEY', kind: 'api-key', description: 'Key', required: true, source: 'owner', set: false, version: null, updated_at: null }] }] : [] }),
    secretsPublicKey: async () => {
      const pair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, ['deriveBits'])) as CryptoKeyPair;
      const raw = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
      return { alg: 'X25519' as const, key: btoa(String.fromCharCode(...raw)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''), key_id: 'k1', sealed_alg: 'X25519-AES256GCM' as const };
    },
  });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/approvals']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'owner', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { calls, options, user: userEvent.setup() };
}

describe('Approvals page', () => {
  it('a card shows the key level the request needs before the owner tries (required_level, D-028)', async () => {
    setup({ hold: { plan: true }, level: 'L2' });
    expect(await screen.findByText('Needs L2 · Proven key', undefined, T)).toBeVisible();
  });

  it('a hold card replaces Approve with Hold to approve, and a plain click approves nothing', async () => {
    const { calls, user } = setup({ hold: { plan: true } });
    const hold = await screen.findByRole('button', { name: /^Hold to approve/ }, T);
    expect(screen.queryByRole('button', { name: /^Approve / })).toBeNull();
    await user.click(hold);
    await user.keyboard('{Enter}');
    await new Promise((r) => setTimeout(r, 50));
    expect(calls).toEqual([]);
  });

  it('a destructive hold card with no plan can still be held and goes through unsigned without a passkey', async () => {
    const { calls } = setup({ hold: { plan: false } });
    const hold = await screen.findByRole('button', { name: /^Hold to approve/ }, T);
    expect(hold).toBeEnabled();
    hold.focus();
    fireEvent.keyDown(hold, { key: 'Enter' });
    await new Promise((r) => setTimeout(r, 2050));
    fireEvent.keyUp(hold, { key: 'Enter' });
    await waitFor(() => expect(calls).toHaveLength(1), T);
    expect(calls[0]!.body).toMatchObject({ hold_ms: expect.any(Number) });
    expect(calls[0]!.body).not.toHaveProperty('webauthn');
    expect(calls[0]!.body).not.toHaveProperty('plan_sha256');
  });

  it('practises the hold gesture, not a click, and sends nothing', async () => {
    const { calls, user } = setup();
    expect(await screen.findByRole('button', { name: 'Practice: Hold to approve' }, T)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Practice: Hold to approve' }));
    expect(screen.queryByText('Practice approved.')).toBeNull();
    expect(calls).toEqual([]);
  });
  it('shows the plan as plain effects, with the raw JSON only under Advanced and no developer copy', async () => {
    setup();
    expect(await screen.findByText('Keeps this app\'s files and databases', {}, T)).toBeInTheDocument();
    expect(screen.getByText(/Opens a path from ollama to open-webui/)).toBeInTheDocument();
    expect(screen.getByText('Needs 8 GB of memory.')).toBeInTheDocument();
    expect(screen.queryByText(/CORE-SEC-2/)).toBeNull();
    expect(screen.queryByText(/gateway scan check/)).toBeNull();
    const adv = screen.getByText(/Advanced: raw plan/).closest('details')!;
    expect(adv).not.toHaveAttribute('open');
    expect(adv).toHaveTextContent(SHA);
  });

  it('an approval that needs a proven key says so in plain words and the card shows the level', async () => {
    const { calls, user } = setup({ passkey: true, levelUnmet: true });
    await user.click(await screen.findByRole('button', { name: /^Approve/ }, T));
    expect(await screen.findByText(/needs your proven key \(L2\).*Settings > Security > Sign-in keys/, {}, T)).toBeInTheDocument();
    expect(await screen.findByText('Needs L2 · Proven key', {}, T)).toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it('with a passkey: approve-options, then approve carrying the plan hash and the signed assertion', async () => {
    const { calls, options, user } = setup({ passkey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    await waitFor(() => expect(screen.getByText(/signs exactly this plan with your passkey/)).toBeInTheDocument(), T);
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    await waitFor(() => expect(calls).toHaveLength(1), T);
    expect(options).toEqual(['act-plan']);
    expect(calls[0]!.body).toEqual({ plan_sha256: SHA, webauthn: { id: 'cred-1', type: 'public-key' } });
  });

  it('refuses to approve when the plan changed since the card was loaded', async () => {
    const { calls, user } = setup({ passkey: true, serverSha: 'sha256:plan-two' });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    expect(await screen.findByText('Could not approve', {}, T)).toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it('an install that needs secrets opens the form and sends them sealed, never as plain text', async () => {
    const { calls, user } = setup({ secrets: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    const dlg = await screen.findByRole('dialog', { name: 'Secrets for Ollama' }, T);
    expect(calls).toEqual([]);
    await user.type(within(dlg).getByLabelText('API_KEY'), 'sk-live-secret-value');
    await user.click(within(dlg).getByRole('button', { name: 'Approve and install' }));
    await waitFor(() => expect(calls).toHaveLength(1), T);
    const body = calls[0]!.body!;
    expect(body.plan_sha256).toBe(SHA);
    expect(body.sealed).toMatchObject({ alg: 'X25519-AES256GCM', kid: 'k1' });
    expect(JSON.stringify(body)).not.toContain('sk-live-secret-value');
  });
});

describe('family invitations through Approvals', () => {
  it.each([
    { replacement: false, name: 'Sam', title: 'Invite Sam' },
    { replacement: true, name: 'Alex', title: 'Replace invite for Alex' },
  ])('shows the one-time link after the owner approves $title', async ({ replacement, name, title }) => {
    const api = new MockApi('owner-demo');
    const row = (await api.users()).find((p) => p.id === 'alex')!;
    const invitePath = '/v1/users/invites/act-invite/claim';
    const replacePath = '/v1/users/alex/invite';
    const optsPath = '/v1/actions/act-invite/approve-options';
    const approvePath = '/v1/actions/act-invite/approve';
    const code = 'family-invite-fixture';
    const link = `https://box.example/signin#enrol=${code}`;
    const writes: Array<[string, unknown]> = [];
    const pending = { id: 'act-invite', type: replacement ? 'users.reinvite' : 'users.invite', state: 'awaiting_approval',
      params: replacement ? { user_id: 'alex', display_name: name, credential_revision: 2 } : { display_name: name, role: 'teen', username: null },
      expires_at: future(), created_at: '2026-11-27T10:00:00Z', updated_at: '2026-11-27T10:00:00Z' };
    const other = { ...pending, id: 'act-other', type: 'app.install', params: { app_id: 'ollama' }, created_at: '2026-11-27T10:01:00Z' };
    // A queued creation from another client is already in Approvals. Replacements
    // still originate in People because they revoke the old credentials.
    let action = replacement ? undefined : pending;
    const http = new HttpApi({ token: 'owner-demo', fetchFn: async (url, req) => {
      const path = new URL(url, window.location.origin).pathname;
      if (req?.method === 'GET' && path === '/v1/actions') return Response.json(action ? [other, action] : [other]);
      if (req?.method === 'POST') {
        const body = req.body ? JSON.parse(String(req.body)) : undefined;
        writes.push([path, body]);
        if (replacement && path === replacePath) {
          action = pending;
          return Response.json(pending, { status: 202 });
        }
        if (path === optsPath) return Response.json({ challenge: 'c', action_sha256: 'invite-fingerprint', expires_at: future(), publicKey: { challenge: 'c' }, password_totp_available: false });
        if (path === approvePath) {
          if (!body.webauthn) return Response.json({ error: 'unauthenticated', reason: 'step_up_required', message: 'Verify this approval.' }, { status: 401 });
          action = { ...pending, state: 'succeeded', updated_at: '2026-11-27T10:02:00Z' };
          return Response.json(action);
        }
        if (path === invitePath && action?.state === 'succeeded' && new Headers(req.headers).get('Authorization') === 'Bearer owner-demo') {
          return Response.json({ ...row, display_name: name, one_time: { enrolment_url: link, enrolment_code: code, expires_at: future() } });
        }
      }
      return Response.json({ error: 'not_found', message: 'Not found.' }, { status: 404 });
    } });
    Object.assign(api, {
      actions: http.actions.bind(http), reissueInvite: http.reissueInvite,
      claimInvite: http.claimInvite, approveOptions: http.approveOptions.bind(http), approve: http.approve.bind(http),
    });
    window.sessionStorage.setItem('onemind.token', 'owner-demo');
    render(<MemoryRouter initialEntries={[replacement ? '/settings/users' : '/approvals?highlight=act-invite']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'owner', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
    const user = userEvent.setup();
    if (replacement) {
      await user.click(await screen.findByRole('button', { name: `Send a new invite to ${name}` }, T));
      await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'New invite' }));
    }
    const approve = await screen.findByRole('button', { name: `Approve ${title}` }, T);
    expect(screen.getByText(replacement ? /signs this person out and clears their existing sign-in credentials/ : /Create a teen account with a one-time invitation/)).toBeVisible();
    expect(screen.queryByText(code)).not.toBeInTheDocument();
    const requests = replacement ? [[replacePath, undefined]] : [];
    expect(writes).toEqual(requests);

    await user.click(approve);
    const dialog = within(await screen.findByRole('dialog', { name: 'Invite a person' }, T));
    expect(dialog.getByLabelText('Invite link')).toHaveValue(link);
    expect(dialog.getByText(code)).toBeVisible();
    expect(dialog.getByRole('img', { name: 'Invite QR code' })).toBeVisible();
    expect(writes).toEqual([...requests, [optsPath, {}], [approvePath, {}],
      [approvePath, { webauthn: { id: 'cred-1', type: 'public-key' } }], [invitePath, undefined]]);
    expect(JSON.stringify({ ...window.sessionStorage, ...window.localStorage })).not.toContain(code);
    await user.click(dialog.getAllByRole('button', { name: 'Close' }).at(-1)!);
    expect(screen.queryByText(code)).not.toBeInTheDocument();
  });
});

it('issues an invitation directly from People after verifying the exact change', async () => {
  const api = new MockApi('owner-demo');
  const input = { display_name: 'Sam', role: 'teen' };
  const operation = { op: 'users.create', target: '', body: { ...input, username: null } };
  const code = 'one-use-invite';
  const link = `https://box.example/signin#enrol=${code}`;
  const writes: Array<[string, unknown, string | null]> = [];
  const http = new HttpApi({ token: 'owner-demo', fetchFn: async (url, req) => {
    const path = new URL(url, window.location.origin).pathname;
    const proof = new Headers(req?.headers).get('OneMind-Step-Up');
    writes.push([path, req?.body ? JSON.parse(String(req.body)) : undefined, proof]);
    if (path === '/v1/auth/step-up/options') return Response.json({ challenge: 'c', publicKey: { challenge: 'c' } });
    if (path === '/v1/auth/step-up') return Response.json({ step_up: 'verified-invite' });
    if (path === '/v1/users' && proof === 'verified-invite') {
      return Response.json({ id: 'sam', ...input, one_time: { enrolment_url: link, enrolment_code: code, expires_at: future() } }, { status: 201 });
    }
    return Response.json({ error: 'unauthenticated', reason: 'step_up_required', message: 'Confirm the invitation',
      details: [{ step_up: { ...operation, required_level: 'L2' } }] }, { status: 401 });
  } });
  Object.assign(api, { createUser: http.createUser.bind(http) });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/settings/users']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'owner', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Invite a person' }, T));
  const form = within(screen.getByRole('dialog', { name: 'Invite a person' }));
  await user.type(form.getByLabelText('Name'), 'Sam');
  await user.selectOptions(form.getByLabelText('Role'), 'teen');
  await user.click(form.getByRole('button', { name: 'Create invite' }));
  expect(await screen.findByLabelText('Invite link', {}, T)).toHaveValue(link);
  expect(writes).toEqual([
    ['/v1/users', input, null],
    ['/v1/auth/step-up/options', operation, null],
    ['/v1/auth/step-up', { credential: { id: 'cred-1', type: 'public-key' } }, null],
    ['/v1/users', input, 'verified-invite'],
  ]);
  expect(JSON.stringify({ ...window.sessionStorage, ...window.localStorage })).not.toContain(code);
});

describe('approveWithStepUp', () => {
  const opts = { challenge: 'c', action_sha256: 'a', plan_sha256: SHA, expires_at: '', publicKey: { challenge: 'c' } };
  const act = { id: 'x', plan_sha256: SHA };

  it('uses a fresh password and authenticator plus the local box code for an L2 approval without a passkey', async () => {
    const availability = { required_level: 'L2', box_available: true, password_totp_available: true };
    const approveOptions = vi.fn()
      .mockRejectedValueOnce(new ApiError(409, 'conflict', 'This needs L2', 'verification_level_unmet', [{ approval_verification: availability }]))
      .mockResolvedValueOnce({ ...opts, challenge: 'mfa-challenge', publicKey: {}, box_code_required: true });
    const approve = vi.fn(async () => ({ id: 'x' }));
    const sign = vi.fn();
    const boxCode = vi.fn(async () => '482913');
    const verification = vi.fn(async () => ({ method: 'password+totp' as const, password: 'a test passphrase', totp: '012345', atBox: true }));
    await approveWithStepUp({ approveOptions, approve }, act, { sign, boxCode, verification });
    expect(verification).toHaveBeenCalledWith(expect.objectContaining({ required_level: 'L2', box: 'alt' }));
    expect(approveOptions).toHaveBeenNthCalledWith(2, 'x', { method: 'password+totp', at_box: true });
    expect(approve).toHaveBeenCalledExactlyOnceWith('x', { plan_sha256: SHA, box_code: '482913',
      password_totp: { challenge: 'mfa-challenge', password: 'a test passphrase', totp: '012345' } });
    expect(sign).not.toHaveBeenCalled();
  });

  it('sends a measured hold with the passkey and reviewed fingerprint', async () => {
    const approve = vi.fn(async () => ({ id: 'x' }));
    const sign = vi.fn(async () => ({ id: 'sig' }));
    const api = { approveOptions: async () => opts, approve } as never;
    await approveWithStepUp(api, act, { passkey: true, hold: { ms: 2000, plan: SHA }, sign });
    expect(approve).toHaveBeenCalledExactlyOnceWith('x', { plan_sha256: SHA, hold_ms: 2000, webauthn: { id: 'sig' } });
    await expect(approveWithStepUp(api, act, { passkey: true, hold: { ms: 2000, plan: 'old' }, sign })).rejects.toThrow('current plan');
    expect(approve).toHaveBeenCalledTimes(1);
  });

  it('during the grace (N-1 b) the code on the box\'s screen goes with the passkey', async () => {
    const approve = vi.fn(async () => ({ id: 'x' }));
    const sign = vi.fn(async () => ({ id: 'sig' }));
    const boxCode = vi.fn(async () => '482913');
    const api = { approveOptions: async () => ({ ...opts, required_level: 'L1', box_code_required: true }), approve } as never;
    await approveWithStepUp(api, act, { passkey: true, sign, boxCode });
    expect(boxCode).toHaveBeenCalledExactlyOnceWith('approve x');
    expect(approve).toHaveBeenCalledExactlyOnceWith('x', { plan_sha256: SHA, box_code: '482913', webauthn: { id: 'sig' } });
  });

  it('a hold without a passkey goes unsigned, and is retried signed only when the gateway asks for step-up', async () => {
    const sign = vi.fn(async () => ({ id: 'sig' }));
    const ok = vi.fn(async () => ({ id: 'x' }));
    await approveWithStepUp({ approveOptions: async () => opts, approve: ok } as never, act, { hold: { ms: 2000, plan: SHA }, sign });
    expect(sign).not.toHaveBeenCalled();
    expect(ok).toHaveBeenCalledExactlyOnceWith('x', { plan_sha256: SHA, hold_ms: 2000 });
    const approve = vi.fn()
      .mockRejectedValueOnce(new ApiError(401, 'unauthenticated', 'passkey needed', 'step_up_required'))
      .mockResolvedValueOnce({ id: 'x' });
    await approveWithStepUp({ approveOptions: async () => opts, approve } as never, act, { hold: { ms: 2000, plan: SHA }, sign });
    expect(approve).toHaveBeenNthCalledWith(2, 'x', { plan_sha256: SHA, hold_ms: 2000, webauthn: { id: 'sig' } });
  });

  it('a hold on an action with no plan carries hold_ms and no plan binding', async () => {
    const approve = vi.fn(async () => ({ id: 'x' }));
    await approveWithStepUp({ approveOptions: async () => ({ ...opts, plan_sha256: undefined }), approve } as never, { id: 'x', plan_sha256: undefined }, { hold: { ms: 2000 } });
    expect(approve).toHaveBeenCalledExactlyOnceWith('x', { hold_ms: 2000 });
  });

  it('a hold on a client without approve-options says passkey approval is unavailable, not that the plan changed', async () => {
    const approve = vi.fn();
    const err = await approveWithStepUp({ approve } as never, act, { hold: { ms: 2000, plan: SHA } }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).reason).not.toBe('plan_changed');
    expect((err as ApiError).message).toMatch(/not available on this client/);
    expect(approve).not.toHaveBeenCalled();
  });

  it('retries once with a passkey when the gateway asks for step-up', async () => {
    const approve = vi.fn()
      .mockRejectedValueOnce(new ApiError(401, 'unauthenticated', 'passkey needed', 'step_up_required'))
      .mockResolvedValueOnce({ id: 'x' });
    const sign = vi.fn(async () => ({ id: 'sig' }));
    await approveWithStepUp({ approveOptions: async () => opts, approve } as never, act, { sign });
    expect(approve).toHaveBeenNthCalledWith(1, 'x', { plan_sha256: SHA });
    expect(approve).toHaveBeenNthCalledWith(2, 'x', { plan_sha256: SHA, webauthn: { id: 'sig' } });
  });

  it('does not approve when signing is cancelled', async () => {
    const approve = vi.fn();
    const sign = vi.fn(async () => { throw new Error('cancelled'); });
    await expect(approveWithStepUp({ approveOptions: async () => opts, approve } as never, act, { passkey: true, sign })).rejects.toThrow('cancelled');
    expect(approve).not.toHaveBeenCalled();
  });

  it('falls back to a plain approve on a gateway without approve-options', async () => {
    const approve = vi.fn(async () => ({ id: 'x' }));
    await approveWithStepUp({ approve } as never, act);
    expect(approve).toHaveBeenCalledWith('x', undefined);
  });
});

describe('toActionPlan', () => {
  it('maps a deleted volume to a high-risk, one-way effect and is undefined without a plan', () => {
    const a = { id: '1', type: 'app.delete_data', params: {}, idempotency_key: 'k', expires_at: '', state: 'awaiting_approval', plan: { summary: 's', volumes: [{ effect: 'deleted' }], warnings: ['All files and databases of this app are deleted. There is no undo.'] }, plan_sha256: 'h' } as unknown as Action;
    const p = toActionPlan(a)!;
    expect(p.undo).toBe('one-way');
    expect(p.effects.find((e) => e.kind === 'data-delete')?.risk).toBe('high');
    expect(toActionPlan({ ...a, plan: undefined })).toBeUndefined();
  });

  it('asks the owner to type the app id when the licence is not green, then approves with accept_licence (#173)', async () => {
    const calls: Array<ApproveBody | undefined> = [];
    const api = new MockApi('owner-demo');
    const action: Action = { id: 'act-lic', type: 'app.install', params: { app_id: 'esphome' }, idempotency_key: 'k', expires_at: future(), state: 'awaiting_approval', plan: PLAN, plan_sha256: SHA, requested_by: { id: 'ops-agent', kind: 'agent', role: 'agent' }, created_at: new Date().toISOString() };
    Object.assign(api, {
      actions: async () => [action], action: async () => action,
      me: async () => ({ principal: { id: 'owner', kind: 'person', role: 'owner' }, token: null, session: null, passkeys: 0, scopes: [], capabilities: [], step_up: { passkeys_active: false, require_passkey_approval: false } }),
      approveOptions: undefined,
      appSecrets: async () => ({ app_id: 'esphome', key_id: 'k1', missing_required: [], secrets: [] }),
      approve: async (_id: string, body?: ApproveBody) => {
        calls.push(body);
        if (body?.accept_licence !== 'esphome') throw new ApiError(409, 'stale_precondition', 'app has licence class unknown', 'licence_unconfirmed');
        return { ...action, state: 'accepted' as const };
      },
    });
    window.sessionStorage.setItem('onemind.token', 'owner-demo');
    render(<MemoryRouter initialEntries={['/approvals']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'owner', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /^approve/i }, T));
    const dialog = await screen.findByRole('alertdialog', {}, T);
    const accept = within(dialog).getByRole('button', { name: /accept licence/i });
    expect(accept).toBeDisabled();
    await user.type(within(dialog).getByLabelText('App id'), 'esphome');
    await user.click(accept);
    await waitFor(() => expect(calls[calls.length - 1]).toEqual({ accept_licence: 'esphome' }), T);
    expect(calls[0]).toBeUndefined();
  });
});
