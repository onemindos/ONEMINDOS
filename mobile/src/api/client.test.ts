// SPDX-License-Identifier: Apache-2.0
import { HttpApi, normalizeHubUrl, type FetchLike } from './client';
import { makeActions } from './fixtures';
import { MockApi } from './mock';
import { ApiError } from './types';

type Call = { url: string; init?: RequestInit };

function fakeFetch(status: number, body: unknown, headers: Record<string, string> = {}): { fn: FetchLike; calls: Call[] } {
  const calls: Call[] = [];
  const fn: FetchLike = async (url, init) => {
    calls.push({ url, init });
    const text = typeof body === 'string' ? body : body === undefined ? '' : JSON.stringify(body);
    return new Response(text, { status, headers });
  };
  return { fn, calls };
}

async function caught(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(ApiError);
    return e as ApiError;
  }
  throw new Error('expected a rejection');
}

describe('normalizeHubUrl', () => {
  it('trims and drops trailing slashes', () => {
    expect(normalizeHubUrl('  https://hub.example:8080/// ')).toBe('https://hub.example:8080');
  });
  it('rejects non-http schemes and garbage', () => {
    expect(() => normalizeHubUrl('ftp://hub')).toThrow(/http/);
    expect(() => normalizeHubUrl('hub.local')).toThrow(/address/);
  });
});

describe('HttpApi', () => {
  it('sends the bearer token to the §3 path on the hub URL', async () => {
    const { fn, calls } = fakeFetch(200, { name: 'Home', version: '0.1.0', hub_node_id: 'abc' });
    const api = new HttpApi({ token: 'tok', baseUrl: 'https://hub.example:8080/', fetchFn: fn });
    await expect(api.instance()).resolves.toEqual({ name: 'Home', version: '0.1.0', hub_node_id: 'abc' });
    expect(calls[0]!.url).toBe('https://hub.example:8080/v1/instance');
    expect((calls[0]!.init!.headers as Record<string, string>).Authorization).toBe('Bearer tok');
  });

  it('posts approve to the encoded action path', async () => {
    const { fn, calls } = fakeFetch(200, { id: 'a/1', state: 'succeeded' });
    await new HttpApi({ token: 't', baseUrl: 'http://h', fetchFn: fn }).approve('a/1');
    expect(calls[0]!.url).toBe('http://h/v1/actions/a%2F1/approve');
    expect(calls[0]!.init!.method).toBe('POST');
  });

  it('maps the §3 error body to its code', async () => {
    const { fn } = fakeFetch(403, { error: 'permission_denied', message: 'agents cannot approve' });
    const e = await caught(new HttpApi({ token: 't', baseUrl: 'http://h', fetchFn: fn }).approve('x'));
    expect(e.status).toBe(403);
    expect(e.code).toBe('permission_denied');
    expect(e.message).toBe('agents cannot approve');
  });

  it('maps a bare 401 to unauthenticated', async () => {
    const { fn } = fakeFetch(401, 'nope');
    expect((await caught(new HttpApi({ token: 't', baseUrl: 'http://h', fetchFn: fn }).nodes())).code).toBe('unauthenticated');
  });

  it('treats an HTML 200 (proxy or SPA fallback) as an error, not data', async () => {
    const { fn } = fakeFetch(200, '<!doctype html><html></html>');
    expect((await caught(new HttpApi({ token: 't', baseUrl: 'http://h', fetchFn: fn }).nodes())).code).toBe('unknown');
  });

  it('turns a thrown fetch into a network error', async () => {
    const fn: FetchLike = async () => {
      throw new TypeError('Network request failed');
    };
    expect((await caught(new HttpApi({ token: 't', baseUrl: 'http://h', fetchFn: fn }).apps())).code).toBe('network');
  });

  it('times out a hub that never answers', async () => {
    const fn: FetchLike = (_u, init) =>
      new Promise((_res, rej) => init?.signal?.addEventListener('abort', () => rej(new Error('aborted'))));
    const e = await caught(new HttpApi({ token: 't', baseUrl: 'http://h', fetchFn: fn, timeoutMs: 20 }).apps());
    expect(e.code).toBe('network');
    expect(e.message).toMatch(/did not answer/);
  });

  it('learns the hub clock offset from the Date header', async () => {
    const hub = new Date(Date.now() + 60_000).toUTCString();
    const { fn } = fakeFetch(200, [], { Date: hub });
    const api = new HttpApi({ token: 't', baseUrl: 'http://h', fetchFn: fn });
    expect(api.hubOffsetMs()).toBeUndefined();
    await api.nodes();
    expect(api.hubOffsetMs()!).toBeGreaterThan(55_000);
  });
});

describe('MockApi follows the §3 rules', () => {
  it('rejects an unknown token', async () => {
    expect((await caught(new MockApi('nope').instance())).code).toBe('unauthenticated');
  });
  it('returns the same action for the same idempotency key', async () => {
    const api = new MockApi('owner-demo');
    const req = { type: 'app.install' as const, params: { app_id: 'jellyfin' }, idempotency_key: 'k1', expires_at: new Date(Date.now() + 3600_000).toISOString() };
    const a = await api.createAction(req);
    const b = await api.createAction(req);
    expect(b.id).toBe(a.id);
    expect(a.state).toBe('awaiting_approval');
  });
  it('fixtures include a pending agent request', () => {
    const pending = makeActions(Date.now()).filter((a) => a.state === 'awaiting_approval');
    expect(pending[0]!.requested_by!.kind).toBe('agent');
  });
});
