// SPDX-License-Identifier: Apache-2.0
import type { CatalogApp } from '../api/types';
import { discoverPhotos } from './discovery';
import { MockPhotosServer } from './mockServer';
import { HttpPhotosApi, UPLOAD_INTEROP_VERSION } from './protocol';

describe('HttpPhotosApi (resumable upload draft)', () => {
  it('sends the draft headers and the declared hash, and resolves the Location', async () => {
    const server = new MockPhotosServer({ token: 'tok' });
    const seen: { method: string; url: string; headers: Record<string, string> }[] = [];
    const api = new HttpPhotosApi({
      baseUrl: server.origin,
      token: 'tok',
      fetchFn: (u, i) => {
        seen.push({ method: i?.method ?? 'GET', url: u, headers: (i?.headers ?? {}) as Record<string, string> });
        return server.fetch(u, i);
      },
    });
    const src = await api.registerSource({ client_id: 'c1', name: 'Phone', platform: 'ios' });
    const url = await api.createUpload({ sourceId: src.id, clientKey: 'k'.repeat(64), hash: `sha256:${'0'.repeat(64)}`, size: 3, fileName: 'Été 1.jpg' });
    expect(url.startsWith(`${server.origin}/v1/photos/uploads/`)).toBe(true);
    const post = seen.find((x) => x.method === 'POST' && x.url.endsWith('/uploads'))!;
    expect(post.headers).toMatchObject({
      'Upload-Draft-Interop-Version': UPLOAD_INTEROP_VERSION,
      'Upload-Complete': '?0',
      'Upload-Length': '3',
      'OneMind-File-Name': encodeURIComponent('Été 1.jpg'),
      Authorization: 'Bearer tok',
    });
    expect(await api.uploadOffset(url)).toEqual({ offset: 0, complete: false });
    const r = await api.appendChunk(url, 0, new Uint8Array([1, 2]), false);
    expect(r.offset).toBe(2);
    const patch = seen.find((x) => x.method === 'PATCH')!;
    expect(patch.headers).toMatchObject({ 'Upload-Offset': '0', 'Upload-Complete': '?0', 'Content-Type': 'application/partial-upload' });
  });

  it('a wrong offset is a conflict, and HEAD reports what the box holds', async () => {
    const server = new MockPhotosServer({ token: 'tok' });
    const api = new HttpPhotosApi({ baseUrl: server.origin, token: 'tok', fetchFn: server.fetch });
    const src = await api.registerSource({ client_id: 'c1', name: 'P', platform: 'android' });
    const url = await api.createUpload({ sourceId: src.id, clientKey: 'k', hash: `sha256:${'0'.repeat(64)}`, size: 10, fileName: 'a' });
    await api.appendChunk(url, 0, new Uint8Array(4), false);
    await expect(api.appendChunk(url, 0, new Uint8Array(4), false)).rejects.toMatchObject({ code: 'conflict', status: 409 });
    expect((await api.uploadOffset(url)).offset).toBe(4);
  });

  it('refuses an upload address on another origin, so the token never leaves the box', async () => {
    const api = new HttpPhotosApi({
      baseUrl: 'https://box.example',
      token: 'tok',
      fetchFn: async () => new Response(null, { status: 201, headers: { Location: 'https://elsewhere.example/u/1' } }),
    });
    await expect(api.createUpload({ sourceId: 's', clientKey: 'k', hash: 'h', size: 1, fileName: 'a' })).rejects.toThrow(/another server/);
  });

  it('maps a dropped connection to a network error', async () => {
    const api = new HttpPhotosApi({ baseUrl: 'https://box.example', token: 't', fetchFn: async () => Promise.reject(new TypeError('Network request failed')) });
    await expect(api.coverage('s')).rejects.toMatchObject({ code: 'network' });
  });
});

describe('discoverPhotos (OneMind catalog)', () => {
  const app = (over: Partial<CatalogApp>) => ({ id: 'photos', installed: true, status: 'running', ...over }) as CatalogApp;
  const live = (hubUrl: string) => ({ mode: 'live' as const, hubUrl, token: 't' });
  it('finds Photos when it is installed and running on an HTTPS hub', () => {
    expect(discoverPhotos(live('https://box.example'), [app({})], '')).toEqual({ state: 'ok', baseUrl: 'https://box.example', demo: false });
  });
  it('says why it cannot back up', () => {
    expect(discoverPhotos(live('https://b'), undefined, '').state).toBe('checking');
    expect(discoverPhotos(live('https://b'), [], '').state).toBe('not_in_catalog');
    expect(discoverPhotos(live('https://b'), [app({ installed: false })], '').state).toBe('not_installed');
    expect(discoverPhotos(live('https://b'), [app({ status: 'failed' })], '')).toEqual({ state: 'not_running', status: 'failed' });
    expect(discoverPhotos(live('http://192.0.2.1:8080'), [app({})], '').state).toBe('needs_https');
  });
  it('the demo always uses the in-memory box', () => {
    expect(discoverPhotos({ mode: 'mock', token: 'owner-demo' }, undefined, 'https://demo.invalid')).toMatchObject({ state: 'ok', demo: true });
  });
});
