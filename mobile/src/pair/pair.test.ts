// SPDX-License-Identifier: Apache-2.0
// Issue 716 acceptance: a mock box that serves a different CA, an expired code and a replayed code is refused,
// and one valid join is accepted. The box here is a test double of /v1/tls/ca.crt and /v1/auth/enrol only.
import type { FetchLike } from '../api/client';
import { toB64url } from '../lib/device';
import { addresses, enrolWithCode, loadPin, markUsed, PairError, readJoin, trustBox, wasUsed } from './pair';
import { caSha256, systemTrust, type BoxProbe, type BoxTrust } from './trust';
import { parseJoinQR } from './joinqr';

const BOX_CA = new TextEncoder().encode('box CA certificate (DER stand-in)');
const OTHER_CA = new TextEncoder().encode('somebody else');
const PIN = caSha256(BOX_CA);
const enc = encodeURIComponent;
const qr = (o: { hub?: string; alt?: string; mdns?: string; ca?: string; code?: string } = {}) =>
  `onemind-join:v2?hub=${enc(o.hub ?? 'https://box1.local:8443')}${o.alt ? `&alt=${enc(o.alt)}` : ''}${o.mdns ? `&mdns=${o.mdns}` : ''}` +
  `&ca=${o.ca ?? PIN}&code=${o.code ?? '7KQ4-M2XP-9D3F'}&kind=phone`;

/** A box reachable at some addresses, serving `ca` there with a chain that does (or does not) verify to it. */
function fakeTrust(serve: Record<string, { ca: Uint8Array; chainOk?: boolean } | 'down'>): BoxTrust & { tried: string[]; pinned: string[] } {
  const tried: string[] = [];
  const pinned: string[] = [];
  return {
    mode: 'pinned',
    tried,
    pinned,
    async probe(url): Promise<BoxProbe> {
      tried.push(url);
      const s = serve[url];
      if (!s || s === 'down') throw new Error('unreachable');
      return { servedCa: caSha256(s.ca), chainOk: s.chainOk ?? true, caDer: toB64url(s.ca) };
    },
    pin: (der) => void pinned.push(der),
    clear: () => void (pinned.length = 0),
  };
}

/** /v1/auth/enrol on the box: one code, valid once, until it expires. */
function enrolBox(o: { code: string; expired?: boolean }) {
  let used = false;
  const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
  const fetchFn: FetchLike = async (url, init) => {
    const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
    calls.push({ url, body });
    const err = (status: number, error: string, message: string, reason?: string) =>
      new Response(JSON.stringify({ error, message, ...(reason ? { reason } : {}) }), { status });
    if (!url.endsWith('/v1/auth/enrol')) return err(404, 'not_found', 'no');
    if (body.code !== o.code || o.expired) return err(401, 'unauthenticated', 'unknown or expired enrolment code', 'code_unknown');
    if (used) return err(401, 'unauthenticated', 'enrolment code already used', 'code_used');
    used = true;
    return new Response(JSON.stringify({ access_token: 'at', expires_at: '2030-01-01T00:00:00Z', refresh_token: 'rt' }), { status: 201 });
  };
  return { fetchFn, calls };
}

describe('pairing from the join QR (issue 716)', () => {
  it('accepts one valid join: hub first, pins the CA from the code, then enrols once', async () => {
    const q = await readJoin(` ${qr({ code: '7KQ4-M2XP-0001' })}\n`);
    const trust = fakeTrust({ 'https://box1.local:8443': { ca: BOX_CA } });
    const pin = await trustBox(q, { trust, now: 0 });
    expect(pin).toEqual({ ca: PIN, hubUrl: 'https://box1.local:8443', addresses: ['https://box1.local:8443'], mode: 'pinned', pinnedAt: '1970-01-01T00:00:00.000Z' });
    expect(trust.pinned).toEqual([toB64url(BOX_CA)]);
    expect(await loadPin()).toEqual(pin);
    const box = enrolBox({ code: 'enrol-code-1' });
    const c = await enrolWithCode(pin.hubUrl, { code: 'enrol-code-1', username: 'ana', password: 'correct horse battery' }, { fetchFn: box.fetchFn });
    expect(c).toEqual({ mode: 'live', hubUrl: 'https://box1.local:8443', token: 'at', auth: 'passkey', expiresAt: '2030-01-01T00:00:00Z', refreshToken: 'rt' });
    expect(box.calls).toEqual([{ url: 'https://box1.local:8443/v1/auth/enrol', body: { code: 'enrol-code-1', password: 'correct horse battery', client: 'app', username: 'ana' } }]);
  });

  it('tries hub, then mdns (on the hub port), then alt, and pins the first that answers', async () => {
    const q = parseJoinQR(qr({ mdns: 'box1.local', alt: 'https://box1.example.net', hub: 'https://hub.example.org:8443' }));
    expect(addresses(q)).toEqual(['https://hub.example.org:8443', 'https://box1.local:8443', 'https://box1.example.net']);
    const trust = fakeTrust({ 'https://hub.example.org:8443': 'down', 'https://box1.local:8443': 'down', 'https://box1.example.net': { ca: BOX_CA } });
    expect((await trustBox(q, { trust })).hubUrl).toBe('https://box1.example.net');
    expect(trust.tried).toEqual(addresses(q));
  });

  it('refuses a box serving a different CA: nothing pinned, no later address tried, nothing sent', async () => {
    const q = parseJoinQR(qr({ alt: 'https://box1.example.net' }));
    const trust = fakeTrust({ 'https://box1.local:8443': { ca: OTHER_CA }, 'https://box1.example.net': { ca: BOX_CA } });
    const before = await loadPin();
    await expect(trustBox(q, { trust })).rejects.toMatchObject({ kind: 'mismatch' });
    expect(trust.tried).toEqual(['https://box1.local:8443']);
    expect(trust.pinned).toEqual([]);
    expect(await loadPin()).toEqual(before);
  });

  it('refuses a served CA whose bytes do not hash to the claimed fingerprint, and a chain that is not from that CA', async () => {
    const q = parseJoinQR(qr());
    const lying: BoxTrust = { ...fakeTrust({}), probe: async () => ({ servedCa: PIN, chainOk: true, caDer: toB64url(OTHER_CA) }) };
    await expect(trustBox(q, { trust: lying })).rejects.toMatchObject({ kind: 'mismatch' });
    const wrongChain = fakeTrust({ 'https://box1.local:8443': { ca: BOX_CA, chainOk: false } });
    await expect(trustBox(q, { trust: wrongChain })).rejects.toMatchObject({ kind: 'mismatch' });
    expect(wrongChain.pinned).toEqual([]);
  });

  it('refuses an expired enrolment code and keeps no session', async () => {
    const box = enrolBox({ code: 'enrol-old', expired: true });
    await expect(enrolWithCode('https://box1.local:8443', { code: 'enrol-old', password: 'correct horse battery' }, { fetchFn: box.fetchFn })).rejects.toMatchObject({
      kind: 'expired',
    });
    expect(await wasUsed('enrol-old')).toBe(false);
  });

  it('refuses a replayed code: the box says used, and this phone then refuses it before sending', async () => {
    const box = enrolBox({ code: 'enrol-2' });
    await enrolWithCode('https://box1.local:8443', { code: 'enrol-2', password: 'correct horse battery' }, { fetchFn: box.fetchFn });
    // Sent again from this phone: refused locally, the box is not asked.
    await expect(enrolWithCode('https://box1.local:8443', { code: 'enrol-2', password: 'x' }, { fetchFn: box.fetchFn })).rejects.toMatchObject({ kind: 'replay' });
    expect(box.calls).toHaveLength(1);
    // Used elsewhere first: the box's code_used is a replay too, and is remembered.
    const other = enrolBox({ code: 'enrol-3' });
    await other.fetchFn('https://b/v1/auth/enrol', { method: 'POST', body: JSON.stringify({ code: 'enrol-3' }) });
    await expect(enrolWithCode('https://box1.local:8443', { code: 'enrol-3', password: 'correct horse battery' }, { fetchFn: other.fetchFn })).rejects.toMatchObject({ kind: 'replay' });
    expect(await wasUsed('enrol-3')).toBe(true);
  });

  it('refuses a join QR this phone already used', async () => {
    await markUsed('7KQ4-M2XP-0002');
    await expect(readJoin(qr({ code: '7KQ4-M2XP-0002' }))).rejects.toMatchObject({ kind: 'replay' });
  });

  it('refuses plain http everywhere: in the code, for a probe and for enrolment', async () => {
    await expect(readJoin(qr({ hub: 'http://box1.local:8080' }))).rejects.toMatchObject({ kind: 'insecure' });
    await expect(readJoin(qr({ hub: 'https://box1.local', alt: 'http://box1.example.net' }))).rejects.toMatchObject({ kind: 'insecure' });
    const box = enrolBox({ code: 'c' });
    await expect(enrolWithCode('http://box1.local:8080', { code: 'c', password: 'p' }, { fetchFn: box.fetchFn })).rejects.toMatchObject({ kind: 'insecure' });
    expect(box.calls).toHaveLength(0);
  });

  it('refuses anything that is not a v2 join code, with the shared parser\'s reason', async () => {
    await expect(readJoin('https://example.org')).rejects.toBeInstanceOf(PairError);
    await expect(readJoin(`onemind-join:v1?code=7KQ4-M2XP-9D3F&ca=${PIN}&hub=${enc('https://box1.local')}`)).rejects.toMatchObject({ kind: 'code' });
    await expect(readJoin(qr({ ca: 'ab' }))).rejects.toMatchObject({ kind: 'code' });
  });

  it('uses the sdk join QR parser unchanged (the copy in src/pair/joinqr.ts matches sdk/ts/src/joinqr.ts)', () => {
    // jest runs from mobile/ (package.json), so these paths are relative to it.
    const { readFileSync } = require('fs') as { readFileSync(path: string, enc: 'utf8'): string };
    const copy = readFileSync('src/pair/joinqr.ts', 'utf8').split('\n');
    copy.splice(1, 2);
    expect(copy.join('\n')).toBe(readFileSync('../sdk/ts/src/joinqr.ts', 'utf8'));
  });

  it('reads every valid shared vector the same way the gateway and Go node do', () => {
    const vectors = require('../../../sdk/testdata/join-qr/vectors.json') as { valid: Array<{ payload: string; expect: object }> };
    for (const v of vectors.valid) expect(parseJoinQR(v.payload)).toEqual(v.expect);
  });

  it('without the native module, takes the CA only through the OS TLS check and still matches it to the code', async () => {
    const fetchFn: FetchLike = async (url) => {
      if (url === 'https://box1.local:8443/v1/tls/ca.crt') return new Response(BOX_CA, { status: 200 });
      throw new TypeError('Network request failed');
    };
    const pin = await trustBox(parseJoinQR(qr()), { trust: systemTrust(fetchFn) });
    expect(pin).toMatchObject({ mode: 'system', ca: PIN });
    await expect(trustBox(parseJoinQR(qr({ hub: 'https://elsewhere.local' })), { trust: systemTrust(fetchFn) })).rejects.toMatchObject({ kind: 'unreachable' });
  });
});
