// SPDX-License-Identifier: Apache-2.0
import { expect, it, vi } from 'vitest';
import { HttpApi } from './client';

vi.mock('../lib/verification', () => ({
  askVerification: vi.fn(),
  chooseVerification: vi.fn(async () => ({ method: 'password+totp', password: 'test password', totp: '123456', atBox: true })),
}));
vi.mock('../lib/boxcode', () => ({ askBoxCode: vi.fn(async () => '654321') }));

it('uses the normal action proof exchange before claiming and confirming the backup kit', async () => {
  const actionPath = '/v1/actions/kit-action';
  const kitPath = '/v1/backups/kit';
  const action = { id: 'kit-action', type: 'backup.kit.issue', state: 'awaiting_approval', plan_sha256: 'kit-plan' };
  const succeeded = { ...action, state: 'succeeded' };
  const oneTime = { groups: ['ABCD', 'EFGH'], check: 'WXYZ', text: 'test emergency kit' };
  const kit = { state: 'issued', positions: [1, 2] };
  const calls: Array<[string, unknown]> = [];
  const api = new HttpApi({ token: 'test-owner', fetchFn: async (url, init) => {
    const path = new URL(url, window.location.origin).pathname;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push([path, body]);
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer test-owner');
    if (path === `${kitPath}/request`) return Response.json(action, { status: 202 });
    if (path === `${actionPath}/approve-options` && body?.method !== 'password+totp') {
      return Response.json({ error: 'conflict', message: 'A proven key is required (L2)', reason: 'verification_level_unmet',
        details: [{ approval_verification: { required_level: 'L2', box_available: true, password_totp_available: true } }] }, { status: 409 });
    }
    if (path === `${actionPath}/approve-options`) return Response.json({ challenge: 'kit-challenge', plan_sha256: 'kit-plan', box_code_required: true });
    if (path === `${actionPath}/approve`) return Response.json(succeeded);
    if (path === `${kitPath}/kit-action/claim`) return Response.json({ action: succeeded, kit, one_time: oneTime });
    if (path === `${kitPath}/confirm`) return Response.json({ ...kit, state: 'confirmed' });
    throw new Error(`Unexpected request ${path}`);
  } });

  const issued = await api.issueKit();
  expect(issued.one_time).toEqual(oneTime);
  await api.confirmKit({ '1': issued.one_time.groups[0]!, '2': issued.one_time.groups[1]! });
  expect(calls).toEqual([
    [`${kitPath}/request`, undefined],
    [`${actionPath}/approve-options`, {}],
    [`${actionPath}/approve-options`, { method: 'password+totp', at_box: true }],
    [`${actionPath}/approve`, { plan_sha256: 'kit-plan', box_code: '654321',
      password_totp: { challenge: 'kit-challenge', password: 'test password', totp: '123456' } }],
    [`${kitPath}/kit-action/claim`, undefined],
    [`${kitPath}/confirm`, { answers: { '1': 'ABCD', '2': 'EFGH' } }],
  ]);
});
