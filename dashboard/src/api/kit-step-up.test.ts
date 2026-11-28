// SPDX-License-Identifier: Apache-2.0
// #1232: once the owner has a passkey, POST /v1/backups/kit answers step_up_required with the request it filed.
// The client signs that request's challenge and asks the same route again, which shows the kit once.
import { expect, it, vi } from 'vitest';
import { HttpApi } from './client';

const h = vi.hoisted(() => ({ sign: vi.fn() }));
vi.mock('../lib/webauthn', () => ({ getPasskey: h.sign }));
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'content-type': 'application/json' },
});
const publicKey = { challenge: 'challenge', rpId: 'localhost', allowCredentials: [] };
const issued = { kit: { state: 'issued', confirmed_at: null, fingerprint: '0123456789abcdef', positions: [2, 9] },
  one_time: { groups: ['ABCD'], check: 'EFGH', text: 'ONEMIND EMERGENCY KIT', disk_key: 'disk-key' } };
const stepUp = json({ error: 'unauthenticated', message: 'approvals need a passkey on this box', reason: 'step_up_required',
  details: [{ action_id: 'kit-action' }] }, 401);

function hub(final: () => Response) {
  const sent: Array<{ path: string; body: unknown }> = [];
  const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, 'http://localhost').pathname;
    const body: unknown = init?.body ? JSON.parse(String(init.body)) : undefined;
    sent.push({ path, body });
    if (path === '/v1/actions/kit-action/approve-options') return json({ challenge: 'challenge', action_sha256: '1'.repeat(64),
      plan_sha256: null, expires_at: '2026-11-27T12:10:00Z', publicKey });
    return body === undefined ? stepUp.clone() : final();
  });
  return { sent, fetchFn, api: new HttpApi({ token: 'test-owner', baseUrl: 'http://localhost', fetchFn }) };
}

it('finishes the kit request with a passkey and returns the one-time kit', async () => {
  h.sign.mockReset().mockResolvedValue({ id: 'credential', response: { signature: 'assertion' } });
  const { api, sent } = hub(() => json(issued, 201));
  const r = await api.issueKit();
  expect(r.one_time.disk_key).toBe('disk-key');
  expect(h.sign).toHaveBeenCalledWith(publicKey);
  expect(sent.map((s) => s.path)).toEqual(['/v1/backups/kit', '/v1/actions/kit-action/approve-options', '/v1/backups/kit']);
  expect(sent[2]?.body).toEqual({ action_id: 'kit-action', webauthn: { id: 'credential', response: { signature: 'assertion' } } });
});

it('never sends the kit request again after the person cancels the passkey', async () => {
  h.sign.mockReset().mockRejectedValue(new Error('Cancelled by owner'));
  const { api, fetchFn } = hub(() => json(issued, 201));
  await expect(api.issueKit()).rejects.toThrow('Cancelled by owner');
  expect(fetchFn).toHaveBeenCalledTimes(2);
});

it('does not retry a signed request the hub refused', async () => {
  h.sign.mockReset().mockResolvedValue({ id: 'credential' });
  const { api, fetchFn } = hub(() => json({ error: 'unauthenticated', message: 'passkey check failed', reason: 'step_up_required',
    details: [{ action_id: 'kit-action' }] }, 401));
  await expect(api.issueKit()).rejects.toThrow('passkey check failed');
  expect(fetchFn).toHaveBeenCalledTimes(3);
});

it('passes any other refusal through untouched', async () => {
  const fetchFn = vi.fn(async () => json({ error: 'conflict', message: 'this kit was already issued; it is never shown twice' }, 409));
  const api = new HttpApi({ token: 'test-owner', baseUrl: 'http://localhost', fetchFn });
  await expect(api.issueKit()).rejects.toThrow('never shown twice');
  expect(fetchFn).toHaveBeenCalledTimes(1);
});
