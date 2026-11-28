// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { HttpApi } from './client';
import { getPasskey } from '../lib/webauthn';

vi.mock('../lib/webauthn', async (importOriginal) => ({
  ...await importOriginal<typeof import('../lib/webauthn')>(),
  getPasskey: vi.fn(),
}));

function rig(body: unknown = {}, status = 200) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const make = (token: string) =>
    new HttpApi({ token, fetchFn: async (url, init) => (calls.push({ url, init: init ?? {} }), new Response(status === 204 ? null : JSON.stringify(body), { status })) });
  return { api: make('tok'), anon: make(''), calls };
}
const hdr = (c: { init: RequestInit }, k: string) => (c.init.headers as Record<string, string>)[k];

describe('HttpApi §12 routes', () => {
  it('askToFix always sends approve=false: a fix is a request, never an approval', async () => {
    const { api, calls } = rig({ id: 'a1' });
    await api.askToFix('alr 1', 'why');
    expect(calls[0]!.url).toBe('/v1/alerts/alr%201/fix');
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ approve: false, reason: 'why' });
  });
  it('sends no Authorization header when there is no credential (sign-in routes)', async () => {
    const { anon, calls } = rig({ access_token: 'x' });
    await anon.loginPassword({ username: 'a', password: 'b' });
    expect(hdr(calls[0]!, 'Authorization')).toBeUndefined();
    expect(JSON.parse(String(calls[0]!.init.body))).toMatchObject({ client: 'app' });
  });
  it('setup sends the setup token as the bearer, not the (empty) session token', async () => {
    const { anon, calls } = rig({ access_token: 'x' });
    await anon.setup('first-boot', { username: 'o', display_name: 'O', password: 'p'.repeat(12) });
    expect(hdr(calls[0]!, 'Authorization')).toBe('Bearer first-boot');
  });
  it('204 answers resolve, and error reasons survive (step-up)', async () => {
    const { api } = rig({}, 204);
    await expect(api.revokeToken('t1')).resolves.toBeUndefined();
    const r = rig({ error: 'unauthenticated', message: 'again', reason: 'step_up_required' }, 401);
    await expect(r.api.createUser({ display_name: 'x', role: 'adult' })).rejects.toMatchObject({ status: 401, reason: 'step_up_required' });
  });
  it('an HTML page from a proxy is an error, not data', async () => {
    const { api } = rig('<html>', 200);
    await expect(api.users()).rejects.toMatchObject({ code: 'unknown' });
  });
});

describe('approve', () => {
  it('sends the plan fingerprint so a tainted agent request can be approved', async () => {
    const { api, calls } = rig({ id: 'a1' });
    await api.approve('a1', { plan_sha256: 'sha256:abc' });
    expect(new URL(calls[0]!.url).pathname).toBe('/v1/actions/a1/approve');
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ plan_sha256: 'sha256:abc' });
  });
  it('sends no body when the action has no fingerprint', async () => {
    const { api, calls } = rig({ id: 'a1' });
    await api.approve('a1');
    expect(calls[0]!.init.body).toBeUndefined();
  });
});

it.each(['issued', 'delivery unavailable', 'assertion unavailable'])(
  'uses the SDK for recovery approval and one-time delivery (%s)', async (outcome) => {
  const path = '/v1/backups/kit';
  const assertion = { id: 'passkey' };
  vi.mocked(getPasskey).mockResolvedValue(assertion);
  const kit = { state: 'issued', fingerprint: '0123456789abcdef', positions: [1, 3] };
  const one_time = { text: 'OFFLINE KIT', groups: ['ABCD', 'EFGH', 'JKLM'], check: 'QRST' };
  let approved = false;
  const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
    expect(init?.method).toBe('POST');
    const pathname = new URL(url).pathname; // the SDK resolves the absolute base URL
    if (pathname === '/v1/actions/a1/approve-options') return Response.json({ publicKey: {}, plan_sha256: 'sha256:abc' });
    if (pathname === '/v1/actions/a1/approve') {
      const body = JSON.parse(String(init?.body));
      if (!body.webauthn) return Response.json({ error: 'unauthenticated', message: 'Sign in', reason: 'step_up_required' }, { status: 401 });
      expect(body).toEqual({ webauthn: assertion, plan_sha256: 'sha256:abc' });
      if (outcome === 'assertion unavailable') return Response.json({ error: 'unavailable', message: 'Try again' }, { status: 503 });
      approved = true;
      return Response.json({ id: 'a1', state: 'succeeded' });
    }
    const key = new Headers(init?.headers).get('Idempotency-Key');
    const action = { id: 'a1', type: 'backup.kit.issue', state: 'awaiting_approval', idempotency_key: key };
    if (url.endsWith('/confirm')) return Response.json({ ...kit, state: 'confirmed' });
    expect(pathname).toBe(path);
    if (!approved) return Response.json(action, { status: 202 });
    return outcome === 'issued' ? Response.json({ action, kit, one_time }, { status: 201 }) :
      Response.json({ error: 'unavailable', message: 'The reply was interrupted' }, { status: 503 });
  });
  const api = new HttpApi({ token: 'owner', fetchFn });
  if (outcome === 'issued') {
    await expect(api.issueKit()).resolves.toMatchObject({ kit, one_time });
    await api.confirmKit({ '1': 'ABCD', '3': 'JKLM' }, kit.fingerprint);
    const confirm = fetchFn.mock.calls.at(-1)!;
    expect(new URL(confirm[0]).pathname).toBe(`${path}/confirm`);
    expect(JSON.parse(String(confirm[1]?.body))).toEqual({ answers: { '1': 'ABCD', '3': 'JKLM' }, fingerprint: kit.fingerprint });
  } else {
    await expect(api.issueKit()).rejects.toMatchObject({ status: 503 });
  }
  expect(fetchFn.mock.calls.filter(([url]) => url.endsWith('/approve-options'))).toHaveLength(1);
  expect(fetchFn.mock.calls.filter(([url]) => url.endsWith('/approve'))).toHaveLength(2);
  const kitCalls = fetchFn.mock.calls.filter(([url]) => url.endsWith(path));
  if (outcome === 'assertion unavailable') {
    expect(kitCalls).toHaveLength(1);
    return;
  }
  expect(kitCalls).toHaveLength(2);
  const [requested, delivered] = kitCalls;
  expect(delivered?.[1]?.body).toBe(requested?.[1]?.body);
  expect(JSON.parse(String(requested?.[1]?.body))).toMatchObject({ approve: false, delivery_token: expect.stringMatching(/^[0-9a-f]{64}$/) });
  expect(new Headers(delivered?.[1]?.headers).get('Idempotency-Key')).toBe(new Headers(requested?.[1]?.headers).get('Idempotency-Key'));
});
