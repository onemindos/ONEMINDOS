// SPDX-License-Identifier: Apache-2.0
// UMB-P07 against a REAL gateway. Skipped unless ONEMIND_LIVE_HUB is set (see live.test.ts).
import { nodeFetch } from '../test/nodeFetch';
import { HttpApi, OP } from './client';

const hub = process.env.ONEMIND_LIVE_HUB;
const token = process.env.ONEMIND_LIVE_TOKEN ?? 'dev-owner-token-change-me';
const d = hub ? describe : describe.skip;

d('hub-side preferences on a real hub', () => {
  const api = new HttpApi({ baseUrl: hub ?? 'http://x', token, fetchFn: nodeFetch });
  it('Appearance: Home is read with an ETag and a theme change survives a second read (UMB-P07)', async () => {
    if (!(await api.features()).has(OP.homeGet)) return; // an older hub
    const first = await api.home();
    expect(first.etag).toMatch(/^"/);
    const flipped = first.home.appearance?.theme === 'dark' ? 'light' : 'dark';
    const { updated_at: _t, ...body } = first.home;
    const saved = await api.saveHome({ ...body, appearance: { ...first.home.appearance, theme: flipped } } as never, first.etag);
    expect(saved.home.appearance?.theme).toBe(flipped);
    expect((await api.home()).home.appearance?.theme).toBe(flipped);
    await expect(api.saveHome(body as never, first.etag)).rejects.toMatchObject({ status: 412 }); // stale ETag
    await api.saveHome({ ...body, appearance: first.home.appearance } as never, saved.etag); // put it back
  });
});
