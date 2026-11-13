// SPDX-License-Identifier: Apache-2.0
// End to end: the phone's real backup engine and HTTP client (mobile/src/photos, branch
// feat/mobile-photos) against a running OneMind gateway with Photos on (PHOTOS-SRV-1).
// Run it with test/photos/run-mobile-e2e.sh, which starts the gateway, copies this file to
// mobile/src/photos/__e2e__/ and runs jest there. Skipped unless ONEMIND_E2E_URL is set.
import type { FetchLike } from '../../api/client';
import { runBackup, type RunDeps } from '../engine';
import { MemoryStore, type BackupSettings } from '../ledger';
import { DemoMedia, type DemoAssetSpec } from '../media';
import { HttpPhotosApi } from '../protocol';

const BASE = process.env.ONEMIND_E2E_URL ?? '';
const TOKEN = process.env.ONEMIND_E2E_TOKEN ?? '';
const TOKEN2 = process.env.ONEMIND_E2E_TOKEN2 ?? '';
// The phone refuses plain HTTP. The test gateway listens on loopback HTTP, so only the transport
// is redirected; routes, headers, bodies and hashes are the real client's.
const NAME = 'https://box.e2e.invalid';
const KB = 1024;
const suite = BASE ? describe : describe.skip;

interface Wire {
  patchBytes: number;
  patches: number;
  creates: number;
  /** On this PATCH number: deliver only half the body, then report a dropped connection. */
  dropOnPatch?: number;
}

// The mobile project has no Node type definitions; these are the few Node APIs used below.
interface NodeBytes extends Uint8Array {
  toString(encoding?: 'utf8'): string;
}
interface NodeResponse {
  statusCode?: number;
  headers: Record<string, string | string[] | undefined>;
  on(event: 'data', listener: (chunk: Uint8Array) => void): void;
  on(event: 'end', listener: () => void): void;
}
interface NodeRequest {
  on(event: 'error', listener: (err: unknown) => void): void;
  write(chunk: Uint8Array): void;
  end(): void;
}
const http = jest.requireActual<{ request(opts: object, cb: (res: NodeResponse) => void): NodeRequest }>('node:http');
const { Buffer } = jest.requireActual<{
  Buffer: { from(x: string | Uint8Array): NodeBytes; concat(list: Uint8Array[]): NodeBytes };
}>('node:buffer');

type Init = { method?: string; headers?: unknown; body?: unknown };

/**
 * The jest-expo preset replaces global fetch with a mock, so the transport is Node's http module.
 * It returns only what protocol.ts reads from a Response: status, ok, headers.get and text().
 */
function httpFetch(url: string, init: Init = {}): Promise<Response> {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const raw = init.body;
    const body = raw == null ? undefined : Buffer.from(typeof raw === 'string' ? raw : (raw as Uint8Array));
    const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
    if (body) headers['Content-Length'] = String(body.length);
    const req = http.request(
      { hostname: u.hostname, port: u.port, path: u.pathname + u.search, method: init.method ?? 'GET', headers },
      (res) => {
        const chunks: Uint8Array[] = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8');
          const status = res.statusCode ?? 0;
          const get = (name: string) => {
            const v = res.headers[name.toLowerCase()];
            return v == null ? null : Array.isArray(v) ? v.join(', ') : String(v);
          };
          resolve({ status, ok: status >= 200 && status < 300, headers: { get }, text: async () => text } as unknown as Response);
        });
      },
    );
    req.on('error', () => reject(new TypeError('Network request failed')));
    if (body) req.write(body);
    req.end();
  });
}

function phone(token: string, clientSpecs: DemoAssetSpec[], wire: Wire) {
  const fetchFn: FetchLike = async (url, init = {}) => {
    const target = url.replace(NAME, BASE);
    const method = (init.method ?? 'GET').toUpperCase();
    if (method === 'POST' && url.endsWith('/v1/photos/uploads')) wire.creates++;
    if (method === 'PATCH') {
      wire.patches++;
      const body = init.body as Uint8Array;
      if (wire.dropOnPatch === wire.patches) {
        const half = body.subarray(0, Math.floor(body.length / 2));
        const headers = { ...(init.headers as Record<string, string>), 'Upload-Complete': '?0' };
        await httpFetch(target, { ...(init as Init), headers, body: half });
        wire.patchBytes += half.length;
        throw new TypeError('Network request failed (connection dropped)');
      }
      wire.patchBytes += body.length;
    }
    return httpFetch(target, init as Init);
  };
  const api = new HttpPhotosApi({ baseUrl: NAME, token, fetchFn });
  const media = new DemoMedia(clientSpecs, [{ id: 'camera', title: 'Camera' }]);
  const store = new MemoryStore();
  const settings: BackupSettings = { enabled: true, wifiOnly: true, chargingOnly: false, albums: 'all' };
  const deps = (): RunDeps => ({
    api, media, store, settings,
    conditions: async () => ({ network: 'wifi', power: 'charging' }),
    platform: 'ios', deviceName: 'E2E phone', trigger: 'manual', chunkSize: 256 * KB, saveEveryMs: 0,
  });
  return { api, store, deps };
}

function spec(i: number, size: number, extra: Partial<DemoAssetSpec> = {}): DemoAssetSpec {
  return { id: `a${i}`, fileName: `IMG_${i}.HEIC`, kind: 'photo', size, seed: 1000 + i, albums: ['camera'], createdAt: 1_700_000_000_000 + i, ...extra };
}

suite('phone backup engine against the OneMind gateway', () => {
  jest.setTimeout(120_000);

  it('backs up a library once, dedupes, and a second run sends nothing', async () => {
    const wire: Wire = { patchBytes: 0, patches: 0, creates: 0 };
    const specs = [
      spec(1, 120 * KB),
      spec(2, 700 * KB),
      spec(3, 1 * KB),
      spec(4, 2048 * KB, { kind: 'video', fileName: 'IMG_4.MOV' }),
      spec(5, 300 * KB),
      spec(6, 300 * KB, { seed: 1005, fileName: 'IMG_5 copy.HEIC' }), // same bytes as a5
    ];
    const p = phone(TOKEN, specs, wire);
    const r1 = await runBackup(p.deps());
    expect(r1).toMatchObject({ outcome: 'completed', uploaded: 5, deduped: 1 });
    const unique = specs.slice(0, 5).reduce((n, s) => n + s.size, 0);
    expect(wire.patchBytes).toBe(unique);
    const l = await p.store.loadLedger();
    expect(l!.coverage).toMatchObject({ total: 6, on_box: 6, backed_up: 0, verified: 0 });

    const before = wire.patchBytes;
    const r2 = await runBackup(p.deps());
    expect(r2).toMatchObject({ outcome: 'completed', uploaded: 0, deduped: 0 });
    expect(wire.patchBytes).toBe(before);
  });

  it('resumes a dropped upload from the box offset; every byte crosses the wire once', async () => {
    const wire: Wire = { patchBytes: 0, patches: 0, creates: 0, dropOnPatch: 3 };
    const p = phone(TOKEN, [spec(20, 1500 * KB, { kind: 'video', fileName: 'long.MOV' })], wire);
    const r1 = await runBackup(p.deps());
    expect(r1).toMatchObject({ outcome: 'stopped', reason: 'connection_lost' });
    expect(wire.patchBytes).toBe(2 * 256 * KB + 128 * KB); // the half chunk did arrive
    wire.dropOnPatch = undefined;
    const r2 = await runBackup(p.deps());
    expect(r2).toMatchObject({ outcome: 'completed', uploaded: 1 });
    expect(wire.patchBytes).toBe(1500 * KB);
    expect(wire.creates).toBe(1);
  });

  it('another person with the same bytes is asked for them in full (no hash oracle)', async () => {
    const wire: Wire = { patchBytes: 0, patches: 0, creates: 0 };
    const p = phone(TOKEN2, [spec(1, 120 * KB)], wire); // same bytes the first person backed up
    const r = await runBackup(p.deps());
    expect(r).toMatchObject({ outcome: 'completed', uploaded: 1, deduped: 0 });
    expect(wire.patchBytes).toBe(120 * KB);
  });

  it('the box refuses plain HTTP before any request, as the phone does', () => {
    expect(() => new HttpPhotosApi({ baseUrl: BASE, token: TOKEN })).toThrow(/HTTPS/);
  });
});
