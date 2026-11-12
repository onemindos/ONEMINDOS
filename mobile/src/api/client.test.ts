// SPDX-License-Identifier: Apache-2.0
import { Features, HttpApi, normalizeHubUrl, OP, type FetchLike } from './client';
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

describe('contract §12 additions', () => {
  const hdr = (c: Call, k: string) => (c.init!.headers as Record<string, string>)[k];

  it('reads features from /openapi.json without a token and normalises path parameters', async () => {
    const spec = {
      paths: {
        '/v1/me': { get: {} },
        '/v1/actions/{action_id}/approve-options': { post: {} },
        '/v1/notifications': { get: {} },
      },
    };
    const { fn, calls } = fakeFetch(200, spec);
    const f = await new HttpApi({ token: 'tok', baseUrl: 'https://h', fetchFn: fn }).features();
    expect(calls[0]!.url).toBe('https://h/openapi.json');
    expect(hdr(calls[0]!, 'Authorization')).toBeUndefined();
    expect(f.has(OP.me)).toBe(true);
    expect(f.has(OP.approveOptions)).toBe(true);
    expect(f.has(OP.events)).toBe(false);
  });

  it('treats an unreadable /openapi.json as a v0 gateway', async () => {
    const { fn } = fakeFetch(500, 'oops');
    const f = await new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn: fn }).features();
    expect(f.source).toBe('unknown');
    expect(f.has(OP.me)).toBe(false);
    expect(Features.none().has(OP.notifications)).toBe(false);
  });

  it('sends OneMind-API-Version: 1 (§12.1)', async () => {
    const { fn, calls } = fakeFetch(200, []);
    await new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn: fn }).nodes();
    expect(hdr(calls[0]!, 'OneMind-API-Version')).toBe('1');
  });

  it('keeps reason and retry_after_s, and maps an unknown code by its status class (§12.2)', async () => {
    const step = await caught(
      new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn: fakeFetch(401, { error: 'unauthenticated', message: 'step up', reason: 'step_up_required' }).fn }).approve('a'),
    );
    expect(step.reason).toBe('step_up_required');
    const limited = await caught(
      new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn: fakeFetch(429, { error: 'rate_limited', message: 'slow down', retry_after_s: 7 }).fn }).nodes(),
    );
    expect(limited.code).toBe('rate_limited');
    expect(limited.retryAfterS).toBe(7);
    const future = await caught(
      new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn: fakeFetch(503, { error: 'brand_new_code', message: 'later' }).fn }).nodes(),
    );
    expect(future.code).toBe('unavailable');
    expect(future.message).toBe('later');
    // API.md §8.4 spelling of the step-up signal.
    const old = await caught(
      new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn: fakeFetch(401, { error: 'unauthenticated', message: 'x', details: [{ problem: 'step_up_required' }] }).fn }).approve('a'),
    );
    expect(old.reason).toBe('step_up_required');
  });

  it('renews an expired session once and repeats the request; parallel 401s share one renewal', async () => {
    let token = 'old';
    const refresh = jest.fn(async () => {
      token = 'new';
      return token;
    });
    const calls: string[] = [];
    const fn: FetchLike = async (_url, init) => {
      const auth = (init!.headers as Record<string, string>).Authorization!;
      calls.push(auth);
      return auth === 'Bearer new'
        ? new Response('[]', { status: 200 })
        : new Response(JSON.stringify({ error: 'unauthenticated', message: 'expired' }), { status: 401 });
    };
    const api = new HttpApi({ tokens: { current: () => token, refresh }, baseUrl: 'https://h', fetchFn: fn });
    await Promise.all([api.nodes(), api.apps()]);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(calls.filter((c) => c === 'Bearer new')).toHaveLength(2);
  });

  it('does not treat a step-up refusal as an expired session', async () => {
    const refresh = jest.fn(async () => 'new');
    const { fn } = fakeFetch(401, { error: 'unauthenticated', message: 'passkey needed', reason: 'step_up_required' });
    const e = await caught(new HttpApi({ tokens: { current: () => 't', refresh }, baseUrl: 'https://h', fetchFn: fn }).approve('a', { plan_sha256: 'p' }));
    expect(e.reason).toBe('step_up_required');
    expect(refresh).not.toHaveBeenCalled();
  });

  it('posts the approve body only when it carries something, and deny with a reason', async () => {
    const { fn, calls } = fakeFetch(200, { id: 'a', state: 'accepted' });
    const api = new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn: fn });
    await api.approve('a', {});
    await api.approve('a', { plan_sha256: 'sha256:p', webauthn: { id: 'c', clientDataJSON: 'd', authenticatorData: 'e', signature: 'f' } });
    await api.deny('a', 'not now');
    expect(calls[0]!.init!.body).toBeUndefined();
    expect(JSON.parse(calls[1]!.init!.body as string)).toEqual({
      plan_sha256: 'sha256:p',
      webauthn: { id: 'c', clientDataJSON: 'd', authenticatorData: 'e', signature: 'f' },
    });
    expect(JSON.parse(calls[2]!.init!.body as string)).toEqual({ reason: 'not now' });
  });

  it('calls the inbox, push and device routes as §12.14 and clients.md name them', async () => {
    const { fn, calls } = fakeFetch(200, {});
    const api = new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn: fn });
    await api.markRead('ntf_1');
    await api.markAllRead();
    await api.pushUnregister('reg/1');
    await api.deviceRequestStatus('dreq_1', 'code-9');
    await api.deviceToken('proof.jwt', 'rt');
    expect(calls.map((c) => `${c.init!.method} ${c.url}`)).toEqual([
      'POST https://h/v1/notifications/ntf_1/read',
      'POST https://h/v1/notifications/read-all',
      'DELETE https://h/v1/push/registrations/reg%2F1',
      'GET https://h/v1/devices/requests/dreq_1',
      'POST https://h/v1/devices/token',
    ]);
    expect(hdr(calls[3]!, 'OneMind-Poll-Code')).toBe('code-9');
    expect(hdr(calls[4]!, 'DPoP')).toBe('proof.jwt');
    expect(hdr(calls[4]!, 'Authorization')).toBeUndefined();
  });

  it('asks for unread notifications with a limit', async () => {
    const { fn, calls } = fakeFetch(200, []);
    await new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn: fn }).notifications({ unread: true });
    expect(calls[0]!.url).toBe('https://h/v1/notifications?unread=true&limit=100');
  });
});

describe('MockApi serves the demo §12 routes', () => {
  it('binds the approval to the plan hash and records how it was approved', async () => {
    const api = new MockApi('owner-demo');
    const opts = await api.approveOptions('act-0001');
    const stale = await caught(api.approve('act-0001', { plan_sha256: 'sha256:other' }));
    expect(stale.reason).toBe('plan_changed');
    const done = await api.approve('act-0001', { plan_sha256: opts.plan_sha256 });
    expect(done.approval).toBe('token');
  });
  it('gives each person an own inbox and none to agents', async () => {
    const owner = new MockApi('owner-demo');
    expect((await owner.notifications({ unread: true })).length).toBe(2);
    expect((await owner.markAllRead()).marked).toBe(2);
    expect(await owner.notifications({ unread: true })).toEqual([]);
    expect((await caught(new MockApi('agent-demo').notifications())).code).toBe('permission_denied');
  });
  it('says who may approve through /v1/me', async () => {
    expect((await new MockApi('owner-demo').me()).capabilities).toContain('can_approve');
    expect((await new MockApi('adult-demo').me()).capabilities).not.toContain('can_approve');
  });
});
