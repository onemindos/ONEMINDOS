// SPDX-License-Identifier: Apache-2.0
// D-028: an owner change the hub wants confirmed with a passkey is confirmed in place and sent once more,
// so People, sharing, standing approvals and agent inputs keep working once the owner holds a proven key.
import { describe, expect, it, vi } from 'vitest';

vi.mock('../lib/webauthn', async (orig) => ({ ...(await orig<typeof import('../lib/webauthn')>()), getPasskey: vi.fn(async () => ({ id: 'cred' })) }));
import { HttpApi } from './client';
import { getPasskey } from '../lib/webauthn';

const STEP = { op: 'users.update', target: 'usr_1', body: { display_name: null, role: 'adult' }, required_level: 'L2' };
const json = (status: number, b: unknown) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });

function hub(options?: () => Response) {
  const calls: Array<{ path: string; method: string; headers: Record<string, string>; body: unknown }> = [];
  const api = new HttpApi({
    token: 'tok',
    fetchFn: async (url, init = {}) => {
      const path = new URL(url, 'http://localhost').pathname;
      const headers = (init.headers ?? {}) as Record<string, string>;
      calls.push({ path, method: String(init.method), headers, body: init.body ? JSON.parse(String(init.body)) : undefined });
      if (path === '/v1/auth/step-up/options') return options ? options() : json(200, { challenge_id: 'c', expires_at: 't', required_level: 'L2', grace: false, publicKey: { challenge: 'abc' } });
      if (path === '/v1/auth/step-up') return json(200, { step_up: 'grant-1', expires_at: 't', level: 'L2' });
      if (headers['OneMind-Step-Up'] === 'grant-1') return json(200, { id: 'usr_1', role: 'adult' });
      return json(401, { error: 'unauthenticated', message: 'needs your proven key (L2)', reason: 'step_up_required', details: [{ step_up: STEP }] });
    },
  });
  return { api, calls };
}

describe('step-up in place', () => {
  it('a People change asks for the passkey once and is sent again with the grant', async () => {
    const { api, calls } = hub();
    await api.updateUser('usr_1', { role: 'adult' });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(['PATCH /v1/users/usr_1', 'POST /v1/auth/step-up/options', 'POST /v1/auth/step-up', 'PATCH /v1/users/usr_1']);
    // What is bound is the hub's own echo of the change, not a body rebuilt here.
    expect(calls[1]!.body).toEqual({ op: STEP.op, target: STEP.target, body: STEP.body });
    expect(getPasskey).toHaveBeenCalledWith({ challenge: 'abc' });
    expect(calls[3]!.headers['OneMind-Step-Up']).toBe('grant-1');
  });

  it('no key at the level: the 409 reaches the screen in the hub\'s words, nothing is retried', async () => {
    const { api, calls } = hub(() => json(409, { error: 'conflict', message: 'this needs your proven key (L2); add one under Settings > Security > Sign-in keys', reason: 'verification_level_unmet' }));
    await expect(api.updateUser('usr_1', { role: 'adult' })).rejects.toMatchObject({ status: 409, reason: 'verification_level_unmet' });
    expect(calls).toHaveLength(2);
  });
});
