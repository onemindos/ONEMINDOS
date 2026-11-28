// SPDX-License-Identifier: Apache-2.0
import { expect, test, vi } from 'vitest';
import { AppClient, defineApp } from '../app-sdk/src/index.js';
import type { OneMind } from '../src/index.js';

test('a hello app has declarations and a narrow SDK', async () => {
  const request = vi.fn(async () => ({ state: 'awaiting_approval' }));
  const call = vi.fn(async () => []);
  const app = new AppClient({ actions: { request }, call } as unknown as OneMind, new Map([['api', 'fixture']]));
  expect(defineApp({ notifications: [{ id: 'hello' }] })).toEqual({ notifications: [{ id: 'hello' }] });
  expect('approve' in app).toBe(false);
  expect('gateway' in app).toBe(false);
  expect(app.ownSecret('api')).toBe('fixture');
  expect(app.ownSecret('other-app/api')).toBeUndefined();
  expect(await app.requestAction({ type: 'app.install', appId: 'hello' })).toMatchObject({ state: 'awaiting_approval' });
  await app.fileRoots();
  expect(call).toHaveBeenCalledWith({ method: 'GET', path: '/v1/files/roots', retry: true });
});
