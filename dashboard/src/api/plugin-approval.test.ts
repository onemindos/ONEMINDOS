// SPDX-License-Identifier: Apache-2.0
import { expect, it, vi } from 'vitest';
import { HttpApi } from './client';

const h = vi.hoisted(() => ({ sign: vi.fn() }));
vi.mock('../lib/webauthn', () => ({ getPasskey: h.sign, webauthnSupported: () => true }));
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'content-type': 'application/json' },
});

it('completes an explicitly requested approval using the gateway action-bound challenge', async () => {
  h.sign.mockReset().mockResolvedValue({ id: 'credential', response: { signature: 'assertion' } });
  const sent: Array<{ path: string; body: Record<string, unknown> }> = [];
  const publicKey = { challenge: 'challenge', rpId: 'localhost', allowCredentials: [] };
  const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, 'http://localhost').pathname;
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
    sent.push({ path, body });
    if (path.endsWith('-options')) return json({ challenge: 'challenge', action_sha256: '1'.repeat(64),
      plan_sha256: 'plan-hash', expires_at: '2026-11-20T12:10:00Z', publicKey });
    if (!body.webauthn) return json({ error: 'unauthenticated', message: 'passkey required', reason: 'step_up_required' }, 401);
    return json({ id: 'key-action', state: 'succeeded', type: 'plugin.key.enroll', params: {} });
  });
  const api = new HttpApi({ token: 'test-owner', baseUrl: 'http://localhost', fetchFn });
  expect((await api.approve('key-action')).state).toBe('succeeded');
  expect(h.sign).toHaveBeenCalledWith(publicKey);
  expect(sent.map(request => request.path)).toEqual([
    '/v1/actions/key-action/approve', '/v1/actions/key-action/approve-options', '/v1/actions/key-action/approve',
  ]);
  expect(sent[2]?.body).toEqual({ webauthn: { id: 'credential', response: { signature: 'assertion' } }, plan_sha256: 'plan-hash' });
});

it('never submits approval after the person cancels the authenticator', async () => {
  h.sign.mockReset().mockRejectedValue(new Error('Cancelled by owner'));
  const fetchFn = vi.fn(async (url: string) => new URL(url, 'http://localhost').pathname.endsWith('-options')
    ? json({ challenge: 'challenge', action_sha256: '1'.repeat(64), plan_sha256: null,
      expires_at: '2026-11-20T12:10:00Z', publicKey: { challenge: 'challenge' } })
    : json({ error: 'unauthenticated', message: 'passkey required', reason: 'step_up_required' }, 401));
  const api = new HttpApi({ token: 'test-owner', baseUrl: 'http://localhost', fetchFn });
  await expect(api.approve('key-action')).rejects.toThrow('Cancelled by owner');
  expect(fetchFn).toHaveBeenCalledTimes(2);
});
