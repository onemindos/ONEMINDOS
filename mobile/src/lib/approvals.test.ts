// SPDX-License-Identifier: Apache-2.0
import { Features, OP, type OneMindApi } from '../api/client';
import { makeActions } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { ApiError, type Action } from '../api/types';
import { v0Api } from '../test/fakes';
import { actionTitle, decide, needsPasskey, principalLabel, REQUEST_TTL_MS, requestAction, sortByRecent } from './approvals';
import { b64url, PasskeyError, type Passkeys } from './webauthn';

const NOW = Date.parse('2026-11-12T12:00:00Z');

async function pendingOf(api: MockApi): Promise<Action> {
  const a = (await api.actions()).find((x) => x.state === 'awaiting_approval');
  if (!a) throw new Error('no pending action in fixtures');
  return a;
}

describe('approval flow', () => {
  it('an owner approves an agent request and the app ends up installed', async () => {
    const api = new MockApi('owner-demo');
    const a = await pendingOf(api);
    expect(a.requested_by).toMatchObject({ kind: 'agent' });
    const r = await decide(api, a, 'approve');
    expect(r).toMatchObject({ ok: true });
    if (r.ok) {
      expect(r.action.state).toBe('succeeded');
      expect(r.action.decided_by).toMatchObject({ kind: 'person', role: 'owner' });
      expect(r.message).toMatch(/Approved \(without a passkey\) and done: Install ollama/);
    }
    expect((await api.apps()).find((x) => x.id === 'ollama')!.installed).toBe(true);
  });

  it('an owner denies, and the action is cancelled', async () => {
    const api = new MockApi('owner-demo');
    const r = await decide(api, await pendingOf(api), 'deny');
    expect(r.ok && r.action.state).toBe('cancelled');
  });

  it('an agent can never approve (403 permission_denied → forbidden)', async () => {
    const api = new MockApi('agent-demo');
    const r = await decide(api, await pendingOf(api), 'approve');
    expect(r).toMatchObject({ ok: false, forbidden: true, code: 'permission_denied' });
  });

  it('an adult cannot deny either', async () => {
    const api = new MockApi('adult-demo');
    expect(await decide(api, await pendingOf(api), 'deny')).toMatchObject({ ok: false, forbidden: true });
  });

  it('approving after expires_at reports expiry', async () => {
    let now = NOW;
    const api = new MockApi('owner-demo', { now: () => now });
    const a = await requestAction(api, 'app.install', 'jellyfin', { now });
    expect(Date.parse(a.expires_at) - now).toBe(REQUEST_TTL_MS);
    now += REQUEST_TTL_MS + 1000;
    const r = await decide(api, a, 'approve');
    expect(r).toMatchObject({ ok: false, code: 'expired', forbidden: false });
  });

  it('the hub refuses an install without a fresh passing scan (§10.3)', async () => {
    const api = new MockApi('owner-demo');
    const a = await requestAction(api, 'app.install', 'mosquitto'); // never scanned in fixtures
    const r = await decide(api, a, 'approve');
    expect(r).toMatchObject({ ok: false, code: 'stale_precondition' });
    expect(!r.ok && r.message).toMatch(/Not scanned/);
  });

  it('a second decision on the same action is a conflict', async () => {
    const api = new MockApi('owner-demo');
    const a = await pendingOf(api);
    await decide(api, a, 'deny');
    expect(await decide(api, a, 'approve')).toMatchObject({ ok: false, code: 'conflict' });
  });

  it('a network failure says nothing was changed', async () => {
    const api = { approve: async () => { throw new ApiError(0, 'network', 'offline'); } } as unknown as OneMindApi;
    const r = await decide(api, { id: 'x', type: 'app.install', params: { app_id: 'a' } } as Action, 'approve');
    expect(!r.ok && r.message).toMatch(/Nothing was changed/);
  });

  it('a request reuses the caller idempotency key', async () => {
    const api = new MockApi('owner-demo');
    const a = await requestAction(api, 'app.install', 'jellyfin', { idempotencyKey: 'same' });
    const b = await requestAction(api, 'app.install', 'jellyfin', { idempotencyKey: 'same' });
    expect(b.id).toBe(a.id);
  });
});

describe('labels', () => {
  it('names actions and principals', () => {
    expect(actionTitle({ type: 'app.remove', params: { app_id: 'ntfy' } })).toBe('Remove ntfy');
    expect(principalLabel({ id: 'hermes-agent', kind: 'agent' })).toBe('agent hermes-agent');
    expect(principalLabel(undefined)).toBe('unknown requester');
  });
  it('sorts newest first', () => {
    const list = [
      { id: 'old', updated_at: '2026-11-10T00:00:00Z' },
      { id: 'new', updated_at: '2026-11-12T00:00:00Z' },
    ] as Action[];
    expect(sortByRecent(list).map((a) => a.id)).toEqual(['new', 'old']);
  });
});

describe('approval with passkey step-up (§12.3, §12.4)', () => {
  const assertion = { id: 'cred', clientDataJSON: 'cd', authenticatorData: 'ad', signature: 'sig' };
  const pending = (over: Partial<Action> = {}): Action => ({ ...makeActions(Date.now())[0]!, plan_sha256: 'sha256:p', ...over });
  const fakePasskeys = (impl?: () => Promise<typeof assertion>): Passkeys & { get: jest.Mock } => ({
    supported: () => true,
    get: jest.fn(impl ?? (async () => assertion)),
    create: jest.fn(),
  });
  const v1 = new Features([OP.approveOptions, OP.preview], 'openapi');
  const opts = { challenge: 'Y2g=', action_sha256: 'sha256:a', plan_sha256: 'sha256:p', expires_at: '2030-01-01T00:00:00Z' };

  it('signs the challenge bound to the plan when the owner has a passkey, and sends plan + assertion', async () => {
    const approve = jest.fn(async () => ({ ...pending(), state: 'accepted' as const, approval: 'passkey' as const }));
    const api = v0Api({ approveOptions: async () => opts, approve });
    const passkeys = fakePasskeys();
    const r = await decide(api, pending({ plan_sha256: 'sha256:p' }), 'approve', { features: v1, passkeys, ownerHasPasskey: true, hubUrl: 'https://onemind.local:8443' });
    expect(r).toMatchObject({ ok: true, message: 'Approved with your passkey: Install ollama (accepted).' });
    expect(passkeys.get).toHaveBeenCalledWith({ challenge: 'Y2g', rpId: 'onemind.local', timeout: 60_000, userVerification: 'required' });
    expect(approve).toHaveBeenCalledWith('act-0001', { plan_sha256: 'sha256:p', webauthn: assertion });
  });

  it('sends no plan hash when the hub has none for the action (approve-options answers null)', async () => {
    const approve = jest.fn(async () => ({ ...pending(), state: 'accepted' as const }));
    const api = v0Api({ approveOptions: async () => ({ ...opts, plan_sha256: null }), approve });
    await decide(api, pending({ plan_sha256: null }), 'approve', { features: v1, ownerHasPasskey: false });
    expect(approve).toHaveBeenCalledWith('act-0001', {});
  });

  it('refuses locally when the hub plan is not the plan on the card', async () => {
    const approve = jest.fn();
    const api = v0Api({ approveOptions: async () => opts, approve });
    const r = await decide(api, pending({ plan_sha256: 'sha256:OLD' }), 'approve', { features: v1, passkeys: fakePasskeys(), ownerHasPasskey: true });
    expect(r).toMatchObject({ ok: false, reason: 'plan_changed' });
    expect(r.message).toMatch(/changed since you opened it/);
    expect(approve).not.toHaveBeenCalled();
  });

  it('without an owner passkey sends only the plan hash; if the hub asks for step-up, signs once and retries', async () => {
    const approve = jest
      .fn()
      .mockRejectedValueOnce(new ApiError(401, 'unauthenticated', 'step up', { reason: 'step_up_required' }))
      .mockResolvedValueOnce({ ...pending(), state: 'accepted', approval: 'passkey' });
    const api = v0Api({ approveOptions: async () => opts, approve });
    const passkeys = fakePasskeys();
    const r = await decide(api, pending(), 'approve', { features: v1, passkeys, ownerHasPasskey: false, hubUrl: 'https://h' });
    expect(r.ok).toBe(true);
    expect(approve.mock.calls[0]).toEqual(['act-0001', { plan_sha256: 'sha256:p' }]);
    expect(approve.mock.calls[1]).toEqual(['act-0001', { plan_sha256: 'sha256:p', webauthn: assertion }]);
  });

  it('always needs a passkey for destructive actions, and says so plainly when the phone has none', async () => {
    const approve = jest.fn();
    const api = v0Api({ approveOptions: async () => opts, approve });
    const r = await decide(api, pending({ risk: 'destructive' }), 'approve', { features: v1, ownerHasPasskey: false, hubUrl: 'https://h' });
    expect(r).toMatchObject({ ok: false, code: 'passkey', reason: 'not_supported' });
    expect(approve).not.toHaveBeenCalled();
  });

  it('a cancelled passkey prompt approves nothing', async () => {
    const approve = jest.fn();
    const api = v0Api({ approveOptions: async () => opts, approve });
    const passkeys = fakePasskeys(async () => {
      throw new PasskeyError('cancelled', 'user cancelled');
    });
    const r = await decide(api, pending(), 'approve', { features: v1, passkeys, ownerHasPasskey: true, hubUrl: 'https://h' });
    expect(r).toMatchObject({ ok: false, message: 'Cancelled. Nothing was approved or changed.' });
    expect(approve).not.toHaveBeenCalled();
  });

  it('deny never asks for a passkey and carries the reason', async () => {
    const deny = jest.fn(async () => ({ ...pending(), state: 'cancelled' as const }));
    const passkeys = fakePasskeys();
    const r = await decide(v0Api({ deny }), pending({ risk: 'destructive' }), 'deny', { features: v1, passkeys, ownerHasPasskey: true, reason: 'not now' });
    expect(r.ok).toBe(true);
    expect(deny).toHaveBeenCalledWith('act-0001', 'not now');
    expect(passkeys.get).not.toHaveBeenCalled();
  });

  it('on a hub without approve-options, answers plan_unchecked with the previewed plan hash', async () => {
    const approve = jest
      .fn()
      .mockRejectedValueOnce(new ApiError(409, 'stale_precondition', 'plan hash required', { reason: 'plan_unchecked' }))
      .mockResolvedValueOnce({ ...pending(), state: 'succeeded' });
    const api = v0Api({ approve, preview: async () => ({ plan: {}, plan_sha256: 'sha256:p' }) });
    const r = await decide(api, pending(), 'approve', { features: new Features([OP.preview], 'openapi'), ownerHasPasskey: false });
    expect(r.ok).toBe(true);
    expect(approve.mock.calls[1]).toEqual(['act-0001', { plan_sha256: 'sha256:p' }]);
  });

  it('names the new §12 refusals', async () => {
    const api = v0Api({ approve: async () => Promise.reject(new ApiError(429, 'rate_limited', 'slow', { retryAfterS: 5 })) });
    expect((await decide(api, pending(), 'approve')).message).toMatch(/try again in 5 s/);
    const api2 = v0Api({ approve: async () => Promise.reject(new ApiError(409, 'policy_refused', 'hostPath volume')) });
    expect((await decide(api2, pending(), 'approve')).message).toMatch(/sandbox refused this plan: hostPath volume/);
  });
});

describe('approval card helpers', () => {
  it('titles §12.5 types by their subject', () => {
    expect(actionTitle({ type: 'node.remove', params: { node_id: 'n1' } })).toBe('node.remove n1');
    expect(actionTitle({ type: 'catalog.refresh', params: {} })).toBe('catalog.refresh');
  });
  it('needs a passkey for destructive and actuate, or always once the owner has one (F-2)', () => {
    expect(needsPasskey({ risk: 'write' }, false)).toBe(false);
    expect(needsPasskey({ risk: 'destructive' }, false)).toBe(true);
    expect(needsPasskey({ risk: 'actuate' }, false)).toBe(true);
    expect(needsPasskey({ risk: 'read' }, true)).toBe(true);
  });
  it('maps base64 to unpadded base64url for the authenticator', () => {
    expect(b64url('ab+/c==')).toBe('ab-_c');
  });
});
