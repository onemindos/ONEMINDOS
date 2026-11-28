// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { HttpApi } from './client';

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
    expect(calls[0]!.url).toBe('/v1/actions/a1/approve');
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ plan_sha256: 'sha256:abc' });
  });
  it('sends no body when the action has no fingerprint', async () => {
    const { api, calls } = rig({ id: 'a1' });
    await api.approve('a1');
    expect(calls[0]!.init.body).toBeUndefined();
  });
});

it.each([201, 503])('uses the SDK to collect the approved kit only once (response %i)', async (status) => {
  const path = '/v1/backups/kit';
  const kit = { state: 'issued', fingerprint: '0123456789abcdef', positions: [1, 3] };
  const one_time = { text: 'OFFLINE KIT', groups: ['ABCD', 'EFGH', 'JKLM'], check: 'QRST' };
  let approved = false;
  const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
    expect(init?.method).toBe('POST');
    if (url.endsWith('/approve-options')) return Response.json({ publicKey: {} });
    if (url.endsWith('/approve')) {
      approved = true;
      return Response.json({ id: 'a1', state: 'succeeded' });
    }
    const key = new Headers(init?.headers).get('Idempotency-Key');
    const action = { id: 'a1', type: 'backup.kit.issue', state: 'awaiting_approval', idempotency_key: key };
    if (url.endsWith('/confirm')) return Response.json({ ...kit, state: 'confirmed' });
    expect(new URL(url).pathname).toBe(path); // the SDK resolves the absolute base URL
    if (!approved) return Response.json(action, { status: 202 });
    return status === 201 ? Response.json({ action, kit, one_time }, { status }) :
      Response.json({ error: 'unavailable', message: 'The reply was interrupted' }, { status });
  });
  const api = new HttpApi({ token: 'owner', fetchFn });
  if (status === 201) {
    await expect(api.issueKit()).resolves.toMatchObject({ kit, one_time });
    await api.confirmKit({ '1': 'ABCD', '3': 'JKLM' }, kit.fingerprint);
    const confirm = fetchFn.mock.calls.at(-1)!;
    expect(new URL(confirm[0]).pathname).toBe(`${path}/confirm`);
    expect(JSON.parse(String(confirm[1]?.body))).toEqual({ answers: { '1': 'ABCD', '3': 'JKLM' }, fingerprint: kit.fingerprint });
  } else {
    await expect(api.issueKit()).rejects.toMatchObject({ status });
  }
  const kitCalls = fetchFn.mock.calls.filter(([url]) => url.endsWith(path));
  expect(kitCalls).toHaveLength(2);
  const [requested, delivered] = kitCalls;
  expect(delivered?.[1]?.body).toBe(requested?.[1]?.body);
  expect(JSON.parse(String(requested?.[1]?.body))).toMatchObject({ approve: false, delivery_token: expect.stringMatching(/^[0-9a-f]{64}$/) });
  expect(new Headers(delivered?.[1]?.headers).get('Idempotency-Key')).toBe(new Headers(requested?.[1]?.headers).get('Idempotency-Key'));
});
