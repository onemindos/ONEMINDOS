// SPDX-License-Identifier: Apache-2.0
// The approval loop (contract §12.4): plan in plain words, passkey step-up bound to the plan hash,
// and the sealed install-secrets form. A stub gateway records exactly what the page sends.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { MockApi } from '../api/mock';
import { ApiError, type Action, type ApproveBody } from '../api/types';
import { toActionPlan } from '../data/adapters';
import { PASSKEY_NOT_USED, PASSKEY_UNAVAILABLE, approveWithStepUp } from '../lib/approve';
import { getPasskey, webauthnSupported } from '../lib/webauthn';
import { SessionProvider } from '../session';

vi.mock('../lib/webauthn', async (orig) => ({
  ...(await orig<typeof import('../lib/webauthn')>()),
  webauthnSupported: vi.fn(() => true),
  getPasskey: vi.fn(async () => ({ id: 'cred-1', type: 'public-key' })),
}));

const T = { timeout: 4000 };
const PLAN = { summary: 'Install Ollama.', objects: [], images: [], volumes: [{ kind: 'PersistentVolumeClaim', effect: 'kept' }], nodes: [], warnings: ['Opens a network path: a to b', 'Needs 8 GB of memory.'], network_paths: [{ from: 'ollama', to: 'open-webui', port: 11434, requirement: 'ollama' }] };
const SHA = 'sha256:plan-one';
const future = () => new Date(Date.now() + 3600_000).toISOString();

function setup(opts: { passkey?: boolean; secrets?: boolean; serverSha?: string; hold?: { plan: boolean; stepUp?: boolean }; legacy?: boolean; wantsPasskey?: boolean; otherOwnerPasskey?: boolean; refuseSigned?: boolean; licenceOnSigned?: boolean } = {}) {
  const calls: Array<{ id: string; body?: ApproveBody }> = [];
  const options: string[] = [];
  const api = new MockApi('owner-demo');
  const action: Action = { id: 'act-plan', type: 'app.install', params: { app_id: 'ollama' }, idempotency_key: 'k', expires_at: future(), state: 'awaiting_approval', plan: PLAN, plan_sha256: SHA, requested_by: { id: 'ops-agent', kind: 'agent', role: 'agent' }, created_at: new Date().toISOString() };
  if (opts.hold) {
    action.approval = { hold: true, hold_ms: 2000, physical: false } as Action['approval'];
    if (!opts.hold.plan) { action.plan = null; action.plan_sha256 = undefined; action.params = {}; action.type = 'machine.delete'; }
  }
  if (opts.legacy) {
    action.type = 'legacy.contact.add';
    action.params = { target: 'Ana', wait_days: 60, cooling_off_days: 14 };
    action.plan = null;
    action.plan_sha256 = undefined;
    action.requested_by = { id: 'owner', kind: 'person', role: 'owner' };
  }
  Object.assign(api, {
    actions: async () => [action],
    action: async () => action,
    me: async () => ({ principal: { id: 'owner', kind: 'person', role: 'owner' }, token: null, session: null, passkeys: opts.passkey && !opts.otherOwnerPasskey ? 1 : 0, scopes: [], capabilities: [], step_up: { passkeys_active: !!opts.passkey, require_passkey_approval: false } }),
    approveOptions: async (id: string) => { options.push(id); return { challenge: 'c', action_sha256: 'a', plan_sha256: opts.hold && !opts.hold.plan ? undefined : (opts.serverSha ?? SHA), expires_at: future(), publicKey: { challenge: 'c' } }; },
    approve: async (id: string, body?: ApproveBody) => {
      if ((opts.hold?.stepUp || opts.wantsPasskey) && !body?.webauthn) { calls.push({ id, body }); throw new ApiError(401, 'unauthenticated', 'passkey needed', 'step_up_required'); }
      if (opts.refuseSigned && body?.webauthn) { calls.push({ id, body }); throw new ApiError(401, 'unauthenticated', 'passkey check failed: passkey belongs to another account', 'step_up_required'); }
      if (opts.licenceOnSigned && body?.webauthn) { calls.push({ id, body }); throw new ApiError(409, 'stale_precondition', 'app has licence class unknown', 'licence_unconfirmed'); }
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

// A rejection queued by one test must not leak into the next if that test fails early.
afterEach(() => {
  vi.mocked(getPasskey).mockReset().mockImplementation(async () => ({ id: 'cred-1', type: 'public-key' }));
  vi.mocked(webauthnSupported).mockReset().mockReturnValue(true);
});

describe('Approvals page', () => {
  it('shows the contact, waits and potential export before a legacy invite is approved', async () => {
    setup({ legacy: true });
    const approve = await screen.findByRole('button', { name: 'Approve Add legacy contact Ana' }, T);
    expect(approve).toBeVisible();
    const impact = screen.getByText(/14-day cooling-off period/);
    expect(impact).toBeVisible();
    expect(impact).toHaveTextContent('60-day claim wait');
    expect(impact).toHaveTextContent('read-only export of your personal files');
    expect(screen.queryByText(/The hub has not described what this request will change/)).toBeNull();
    expect(screen.getByText('Technical details').closest('details')).not.toHaveAttribute('open');
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

  it('with a passkey: approve-options, then approve carrying the plan hash and the signed assertion', async () => {
    const { calls, options, user } = setup({ passkey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    await waitFor(() => expect(screen.getByText(/signs exactly this plan with your passkey/)).toBeInTheDocument(), T);
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    await waitFor(() => expect(calls).toHaveLength(1), T);
    expect(options).toEqual(['act-plan']);
    expect(calls[0]!.body).toEqual({ plan_sha256: SHA, webauthn: { id: 'cred-1', type: 'public-key' } });
  });

  it('the first passkey prompt was dismissed: shows the passkey prompt, then approves with it', async () => {
    const { calls, user } = setup({ passkey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    // The browser does not produce a passkey on the first try (no tap, or it was dismissed).
    vi.mocked(getPasskey).mockRejectedValueOnce(new DOMException('dismissed', 'NotAllowedError'));
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    const dlg = await screen.findByRole('alertdialog', { name: 'Use your passkey to approve' }, T);
    expect(calls.filter((c) => c.body?.webauthn)).toEqual([]);
    await user.click(within(dlg).getByRole('button', { name: 'Use your passkey' }));
    await waitFor(() => expect(calls.some((c) => c.body?.webauthn)).toBe(true), T);
    expect(calls.at(-1)!.body).toMatchObject({ plan_sha256: SHA, webauthn: { id: 'cred-1' } });
    await waitFor(() => expect(screen.queryByRole('alertdialog', { name: 'Use your passkey to approve' })).toBeNull(), T);
  });

  it('signed in with a password and no passkey: says so in plain words, with no dead prompt', async () => {
    const { calls, user } = setup({ passkey: false, wantsPasskey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    await waitFor(() => expect(screen.getByText(/Add a passkey in Account and security/)).toBeInTheDocument(), T);
    vi.mocked(getPasskey).mockRejectedValueOnce(new DOMException('dismissed', 'NotAllowedError'));
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    expect(await screen.findByText(/You have no passkey yet/, {}, T)).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog', { name: 'Use your passkey to approve' })).toBeNull();
    expect(calls.filter((c) => c.body?.webauthn)).toEqual([]);
  });

  it('the page does not sign at first and the gateway asks for a passkey: signs the retry with no prompt', async () => {
    const { calls, user } = setup({ passkey: false, wantsPasskey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    await waitFor(() => expect(calls.some((c) => c.body?.webauthn)).toBe(true), T);
    expect(calls[0]!.body).not.toHaveProperty('webauthn');
    expect(screen.queryByRole('alertdialog', { name: 'Use your passkey to approve' })).toBeNull();
  });

  it('the forced retry fails again: says the passkey was not used, closes the prompt, approves nothing', async () => {
    const { calls, user } = setup({ passkey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    vi.mocked(getPasskey).mockRejectedValueOnce(new DOMException('dismissed', 'NotAllowedError')).mockRejectedValueOnce(new DOMException('dismissed', 'NotAllowedError'));
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    const dlg = await screen.findByRole('alertdialog', { name: 'Use your passkey to approve' }, T);
    await user.click(within(dlg).getByRole('button', { name: 'Use your passkey' }));
    expect(await screen.findByText('Your passkey was not used', {}, T)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('alertdialog', { name: 'Use your passkey to approve' })).toBeNull(), T);
    expect(calls).toEqual([]);
  });

  it('Cancel on the passkey prompt closes it and sends nothing', async () => {
    const { calls, user } = setup({ passkey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    vi.mocked(getPasskey).mockRejectedValueOnce(new DOMException('dismissed', 'NotAllowedError'));
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    const dlg = await screen.findByRole('alertdialog', { name: 'Use your passkey to approve' }, T);
    await user.click(within(dlg).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog', { name: 'Use your passkey to approve' })).toBeNull(), T);
    expect(calls).toEqual([]);
  });

  it('a browser without WebAuthn (the page signs nothing, the hub asks): plain message, not the raw TypeError, no dead prompt', async () => {
    vi.mocked(webauthnSupported).mockReturnValue(false);
    // What a browser with no navigator.credentials throws when getPasskey reaches for it.
    vi.mocked(getPasskey).mockRejectedValue(new TypeError("Cannot read properties of undefined (reading 'get')"));
    const { calls, user } = setup({ passkey: true, wantsPasskey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    expect(await screen.findByText(/cannot use a passkey/, {}, T)).toBeInTheDocument();
    expect(screen.queryByText(/Cannot read properties/)).toBeNull();
    expect(screen.queryByRole('alertdialog', { name: 'Use your passkey to approve' })).toBeNull();
    expect(calls.filter((c) => c.body?.webauthn)).toEqual([]);
  });

  it('another owner has a passkey but this person has none: says "no passkey yet", no prompt loop', async () => {
    const { calls, user } = setup({ passkey: true, otherOwnerPasskey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    vi.mocked(getPasskey).mockRejectedValueOnce(new DOMException('dismissed', 'NotAllowedError'));
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    expect(await screen.findByText(/You have no passkey yet/, {}, T)).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog', { name: 'Use your passkey to approve' })).toBeNull();
    expect(calls).toEqual([]);
  });

  it('the typed install secrets survive the passkey prompt and are sent sealed with the passkey', async () => {
    const { calls, user } = setup({ secrets: true, passkey: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    const form = await screen.findByRole('dialog', { name: 'Secrets for Ollama' }, T);
    await user.type(within(form).getByLabelText('API_KEY'), 'sk-live-secret-value');
    vi.mocked(getPasskey).mockRejectedValueOnce(new DOMException('dismissed', 'NotAllowedError'));
    await user.click(within(form).getByRole('button', { name: 'Approve and install' }));
    const dlg = await screen.findByRole('alertdialog', { name: 'Use your passkey to approve' }, T);
    expect(screen.getByRole('dialog', { name: 'Secrets for Ollama' })).toBeInTheDocument();
    await user.click(within(dlg).getByRole('button', { name: 'Use your passkey' }));
    await waitFor(() => expect(calls).toHaveLength(1), T);
    expect(calls[0]!.body).toMatchObject({ sealed: { alg: 'X25519-AES256GCM' }, webauthn: { id: 'cred-1' } });
    expect(JSON.stringify(calls[0]!.body)).not.toContain('sk-live-secret-value');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Secrets for Ollama' })).toBeNull(), T);
  });

  it('a signed request the hub refuses shows the hub\'s reason, not "passkey not used", and no prompt', async () => {
    const { calls, user } = setup({ passkey: true, refuseSigned: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    expect(await screen.findByText(/passkey belongs to another account/, {}, T)).toBeInTheDocument();
    expect(screen.queryByText('Your passkey was not used')).toBeNull();
    expect(screen.queryByRole('alertdialog', { name: 'Use your passkey to approve' })).toBeNull();
    expect(calls).toHaveLength(1);
  });

  it('after the passkey prompt the hub asks for the licence: the prompt closes and only the licence dialog is left', async () => {
    const { user } = setup({ passkey: true, licenceOnSigned: true });
    await screen.findByText('Keeps this app\'s files and databases', {}, T);
    vi.mocked(getPasskey).mockRejectedValueOnce(new DOMException('dismissed', 'NotAllowedError'));
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    const dlg = await screen.findByRole('alertdialog', { name: 'Use your passkey to approve' }, T);
    await user.click(within(dlg).getByRole('button', { name: 'Use your passkey' }));
    await screen.findByRole('alertdialog', { name: /Accept the licence/ }, T);
    expect(screen.queryByRole('alertdialog', { name: 'Use your passkey to approve' })).toBeNull();
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

describe('approveWithStepUp', () => {
  const opts = { challenge: 'c', action_sha256: 'a', plan_sha256: SHA, expires_at: '', publicKey: { challenge: 'c' } };
  const act = { id: 'x', plan_sha256: SHA };

  it('sends a measured hold with the passkey and reviewed fingerprint', async () => {
    const approve = vi.fn(async () => ({ id: 'x' }));
    const sign = vi.fn(async () => ({ id: 'sig' }));
    const api = { approveOptions: async () => opts, approve } as never;
    await approveWithStepUp(api, act, { passkey: true, hold: { ms: 2000, plan: SHA }, sign });
    expect(approve).toHaveBeenCalledExactlyOnceWith('x', { plan_sha256: SHA, hold_ms: 2000, webauthn: { id: 'sig' } });
    await expect(approveWithStepUp(api, act, { passkey: true, hold: { ms: 2000, plan: 'old' }, sign })).rejects.toThrow('current plan');
    expect(approve).toHaveBeenCalledTimes(1);
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

  it('maps only a cancelled or dismissed passkey to passkey_not_used, other sign errors pass through', async () => {
    const approve = vi.fn();
    const api = { approveOptions: async () => opts, approve } as never;
    const cancelled = await approveWithStepUp(api, act, { passkey: true, sign: async () => { throw new DOMException('dismissed', 'NotAllowedError'); } }).catch((e: unknown) => e);
    expect(cancelled).toBeInstanceOf(ApiError);
    expect((cancelled as ApiError).reason).toBe(PASSKEY_NOT_USED);
    const wrongHost = new DOMException('The relying party ID is not a registrable domain suffix', 'SecurityError');
    const other = await approveWithStepUp(api, act, { passkey: true, sign: async () => { throw wrongHost; } }).catch((e: unknown) => e);
    expect(other).toBe(wrongHost);
    expect(approve).not.toHaveBeenCalled();
  });

  it('with no WebAuthn in the browser, a signing TypeError becomes passkey_unavailable', async () => {
    const approve = vi.fn();
    vi.mocked(webauthnSupported).mockReturnValue(false);
    vi.mocked(getPasskey).mockRejectedValue(new TypeError("Cannot read properties of undefined (reading 'get')"));
    const api = { approveOptions: async () => opts, approve } as never;
    for (const o of [{ passkey: true }, {}]) {
      const rejected = o.passkey ? api : { approveOptions: async () => opts, approve: vi.fn().mockRejectedValue(new ApiError(401, 'unauthenticated', 'passkey needed', 'step_up_required')) } as never;
      const err = await approveWithStepUp(rejected, act, o).catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).reason).toBe(PASSKEY_UNAVAILABLE);
    }
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
