// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
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
