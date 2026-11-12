// SPDX-License-Identifier: Apache-2.0
import { MockApi } from '../api/mock';
import { ApiError, type Action } from '../api/types';
import type { OneMindApi } from '../api/client';
import { actionTitle, decide, principalLabel, REQUEST_TTL_MS, requestAction, sortByRecent } from './approvals';

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
      expect(r.message).toMatch(/Approved and done: Install ollama/);
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
