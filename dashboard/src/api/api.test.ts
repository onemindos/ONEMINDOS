import { describe, expect, it, vi } from 'vitest';
import { HttpApi } from './client';
import { makeApps, makeNodes } from './fixtures';
import { MockApi } from './mock';
import { ApiError } from './types';

function jsonResponse(status: number, body: unknown) {
  return new Response(body === undefined ? '' : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('HttpApi (contract §3)', () => {
  it('sends the bearer token and hits the right path', async () => {
    const f = vi.fn().mockResolvedValue(jsonResponse(200, []));
    const api = new HttpApi({ token: 'tkn', baseUrl: 'http://hub:8080/', fetchFn: f });
    await api.nodes();
    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe('http://hub:8080/v1/nodes');
    expect(init.method).toBe('GET');
    expect(init.headers.Authorization).toBe('Bearer tkn');
  });

  it('POSTs actions as JSON', async () => {
    const f = vi.fn().mockResolvedValue(jsonResponse(201, { id: 'a1', state: 'awaiting_approval' }));
    const api = new HttpApi({ token: 't', fetchFn: f });
    const body = {
      type: 'app.install' as const,
      params: { app_id: 'jellyfin' },
      idempotency_key: 'k',
      expires_at: '2026-11-11T23:00:00Z',
    };
    await api.createAction(body);
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe('/v1/actions');
    expect(init.method).toBe('POST');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual(body);
  });

  it('turns a §3 error body into ApiError with its code', async () => {
    const f = vi.fn().mockResolvedValue(jsonResponse(403, { error: 'permission_denied', message: 'no' }));
    const api = new HttpApi({ token: 't', fetchFn: f });
    await expect(api.approve('x')).rejects.toMatchObject({ status: 403, code: 'permission_denied' });
  });

  it('maps a bare 401 to unauthenticated and network failure to network', async () => {
    const api401 = new HttpApi({ token: 't', fetchFn: vi.fn().mockResolvedValue(new Response('', { status: 401 })) });
    await expect(api401.instance()).rejects.toMatchObject({ code: 'unauthenticated' });
    const apiNet = new HttpApi({ token: 't', fetchFn: vi.fn().mockRejectedValue(new TypeError('boom')) });
    await expect(apiNet.instance()).rejects.toMatchObject({ code: 'network', status: 0 });
  });

  it('learns the hub clock offset from the Date header', async () => {
    const hub = Date.now() + 5 * 60_000;
    const res = new Response('[]', {
      status: 200,
      headers: { 'Content-Type': 'application/json', Date: new Date(hub).toUTCString() },
    });
    const api = new HttpApi({ token: 't', fetchFn: vi.fn().mockResolvedValue(res) });
    expect(api.hubOffsetMs()).toBeUndefined();
    await api.nodes();
    expect(Math.abs(api.hubOffsetMs()! - 5 * 60_000)).toBeLessThan(2_000);
  });

  it('rejects a 2xx body that is not JSON (for example an HTML fallback page)', async () => {
    const html = new Response('<!doctype html><title>x</title>', {
      status: 200,
      headers: { 'Content-Type': 'text/html' },
    });
    const api = new HttpApi({ token: 'anything', fetchFn: vi.fn().mockResolvedValue(html) });
    await expect(api.instance()).rejects.toMatchObject({ status: 200, code: 'unknown' });
  });

  it('rejects a list route whose 2xx body is not an array', async () => {
    const api = new HttpApi({ token: 't', fetchFn: vi.fn().mockResolvedValue(jsonResponse(200, { nodes: [] })) });
    await expect(api.nodes()).rejects.toMatchObject({ status: 200, code: 'unknown' });
    const empty = new HttpApi({ token: 't', fetchFn: vi.fn().mockResolvedValue(new Response('', { status: 200 })) });
    await expect(empty.actions()).rejects.toMatchObject({ code: 'unknown' });
  });

  it('URL-encodes path ids', async () => {
    const f = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    await new HttpApi({ token: 't', fetchFn: f }).node('a/b');
    expect(f.mock.calls[0]![0]).toBe('/v1/nodes/a%2Fb');
  });
});

describe('fixtures (contract §2–§4)', () => {
  const now = Date.parse('2026-11-11T22:00:00Z');
  const nodes = makeNodes(now);

  it('cover hub x86, rpi5, jetson-orin and vm-do, with one stale and one offline', () => {
    expect(nodes.map((n) => n.board).sort()).toEqual(['jetson-orin', 'rpi5', 'vm-do', 'x86_64-efi']);
    expect(nodes.find((n) => n.role === 'hub')?.board).toBe('x86_64-efi');
    expect(nodes.filter((n) => n.status === 'stale')).toHaveLength(1);
    expect(nodes.filter((n) => n.status === 'offline')).toHaveLength(1);
  });

  it('use the heartbeat schema and never carry IPs or MACs', () => {
    for (const n of nodes) {
      expect(n.schema).toBe('onemind.node.status/v1');
      expect(n.node_id).toMatch(/^[0-9a-f]{12}$/);
      const s = JSON.stringify(n);
      expect(s).not.toMatch(/\b\d{1,3}(\.\d{1,3}){3}\b/);
      expect(s).not.toMatch(/([0-9a-f]{2}:){5}[0-9a-f]{2}/i);
    }
  });

  it('have three apps', () => {
    expect(makeApps()).toHaveLength(3);
  });
});

describe('MockApi follows the §3 rules', () => {
  const req = (key: string) => ({
    type: 'app.install' as const,
    params: { app_id: 'jellyfin' },
    idempotency_key: key,
    expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  });

  it('rejects an unknown token with 401', async () => {
    await expect(new MockApi('nope').nodes()).rejects.toMatchObject({ status: 401, code: 'unauthenticated' });
  });

  it('returns the same action for the same idempotency key', async () => {
    const api = new MockApi('owner-demo');
    const a = await api.createAction(req('k1'));
    const b = await api.createAction(req('k1'));
    expect(b.id).toBe(a.id);
    expect(a.state).toBe('awaiting_approval');
    expect((await api.actions()).filter((x) => x.idempotency_key === 'k1')).toHaveLength(1);
  });

  it('lets an agent request but never approve', async () => {
    const agent = new MockApi('agent-demo');
    const a = await agent.createAction(req('k2'));
    expect(a.requested_by?.kind).toBe('agent');
    const err = await agent.approve(a.id).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 403, code: 'permission_denied' });
  });

  it('refuses requests from an adult (not owner, not agent)', async () => {
    await expect(new MockApi('adult-demo').createAction(req('k3'))).rejects.toMatchObject({ status: 403 });
  });

  it('approve installs the app; deny cancels', async () => {
    const api = new MockApi('owner-demo');
    const a = await api.createAction(req('k4'));
    expect((await api.approve(a.id)).state).toBe('succeeded');
    expect((await api.apps()).find((x) => x.id === 'jellyfin')?.installed).toBe(true);
    const b = await api.createAction({ ...req('k5'), params: { app_id: 'ollama' } });
    expect((await api.deny(b.id)).state).toBe('cancelled');
  });

  it('approving after expires_at returns 409 expired', async () => {
    let t = Date.now();
    const api = new MockApi('owner-demo', { now: () => t });
    const a = await api.createAction({ ...req('k6'), expires_at: new Date(t + 1000).toISOString() });
    t += 5000;
    await expect(api.approve(a.id)).rejects.toMatchObject({ status: 409, code: 'expired' });
  });
});
