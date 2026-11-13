// SPDX-License-Identifier: Apache-2.0
// In-memory stand-in for the box's Photos backup API (mobile/docs/photos-backup-api.md), used by
// the tests and by the demo. It keeps a running SHA-256 per upload instead of the bytes, so the
// demo stays light on a phone. Rules it follows (photos study §1.3, §4.4):
// - receipts are per source; `check` answers `have` only from this source's own receipts, so one
//   person's phone can never learn what another person holds (no hash oracle, B5);
// - an upload whose final hash differs from the declared one is refused (409, conflict);
// - offsets must match exactly (409 with the true Upload-Offset otherwise);
// - a dropped connection keeps the bytes that arrived, and HEAD reports them (B2).
import { sha256 } from '@noble/hashes/sha2.js';
import { bytesToHex } from '@noble/hashes/utils.js';
import type { FetchLike } from '../api/client';
import type { Coverage } from './protocol';

type Hasher = ReturnType<typeof sha256.create>;

interface Upload {
  id: string;
  sourceId: string;
  clientKey: string;
  hash: string;
  length: number;
  offset: number;
  hasher: Hasher;
  complete: boolean;
}

export interface MockFaults {
  /** The next N PATCH requests fail before any byte arrives. */
  failPatches?: number;
  /** The next PATCH stores only this many bytes, then the connection drops. */
  cutNextPatchAfter?: number;
}

export class MockPhotosServer {
  readonly origin: string;
  private readonly token: string;
  private readonly sources = new Map<string, { id: string; client_id: string; name: string; platform: string }>();
  /** sourceId → client_key → hash */
  private readonly receipts = new Map<string, Map<string, string>>();
  private readonly uploads = new Map<string, Upload>();
  private seq = 0;
  faults: MockFaults = {};
  latencyMs: number;
  /** Fraction of on-box items that the demo reports as in a box backup / restore-verified. */
  coverageRatio = { backed_up: 1, verified: 1 };
  readonly stats = { bytesReceived: 0, patches: 0, uploadsCreated: 0, uploadsCompleted: 0, storedBlobs: 0 };
  private readonly blobs = new Set<string>();

  constructor(opts: { origin?: string; token: string; latencyMs?: number }) {
    this.origin = opts.origin ?? 'https://photos.demo.invalid';
    this.token = opts.token;
    this.latencyMs = opts.latencyMs ?? 0;
  }

  /** Test helper: the receipts the box holds for a source. */
  receiptsFor(sourceId: string): Map<string, string> {
    return this.receipts.get(sourceId) ?? new Map();
  }

  readonly fetch: FetchLike = async (input, init = {}) => {
    if (this.latencyMs) await new Promise((r) => setTimeout(r, this.latencyMs));
    const url = new URL(input);
    const method = (init.method ?? 'GET').toUpperCase();
    const h = new Headers(init.headers as HeadersInit);
    if (url.protocol !== 'https:') throw new TypeError('Network request failed (mock box speaks HTTPS only)');
    if (h.get('Authorization') !== `Bearer ${this.token}`) return json(401, { error: 'unauthenticated', message: 'Unknown token' });
    const p = url.pathname;

    if (method === 'POST' && p === '/v1/photos/sources') return this.registerSource(String(init.body ?? ''));
    let m = /^\/v1\/photos\/sources\/([^/]+)\/check$/.exec(p);
    if (method === 'POST' && m) return this.check(decodeURIComponent(m[1]!), String(init.body ?? ''));
    m = /^\/v1\/photos\/sources\/([^/]+)\/coverage$/.exec(p);
    if (method === 'GET' && m) return this.coverage(decodeURIComponent(m[1]!));
    if (method === 'POST' && p === '/v1/photos/uploads') return this.create(h);
    m = /^\/v1\/photos\/uploads\/([^/]+)$/.exec(p);
    if (m) {
      const up = this.uploads.get(m[1]!);
      if (!up) return json(404, { error: 'not_found', message: 'No such upload' });
      if (method === 'HEAD') return new Response(null, { status: 204, headers: offsetHeaders(up) });
      if (method === 'PATCH') return this.patch(up, h, init.body);
    }
    return json(404, { error: 'not_found', message: `${method} ${p}` });
  };

  private registerSource(body: string) {
    const req = JSON.parse(body) as { client_id?: string; name?: string; platform?: string };
    if (!req.client_id) return json(400, { error: 'bad_request', message: 'client_id is required' });
    for (const s of this.sources.values()) if (s.client_id === req.client_id) return json(200, s);
    const s = { id: `src_${++this.seq}`, client_id: req.client_id, name: req.name ?? 'Phone', platform: req.platform ?? 'other' };
    this.sources.set(s.id, s);
    this.receipts.set(s.id, new Map());
    return json(201, s);
  }

  private check(sourceId: string, body: string) {
    const mine = this.receipts.get(sourceId);
    if (!mine) return json(404, { error: 'not_found', message: 'Unknown source' });
    const { items } = JSON.parse(body) as { items: { client_key: string; size: number; hash: string }[] };
    if (items.length > 500) return json(400, { error: 'bad_request', message: 'At most 500 items' });
    const held = new Set(mine.values());
    return json(200, {
      items: items.map((it) => {
        if (mine.get(it.client_key) === it.hash) return { client_key: it.client_key, status: 'have' };
        // Same bytes already received from this source under another key (a duplicate on the
        // phone): record the receipt, no upload. Never matched across sources.
        if (held.has(it.hash)) {
          mine.set(it.client_key, it.hash);
          return { client_key: it.client_key, status: 'have' };
        }
        return { client_key: it.client_key, status: 'need' };
      }),
    });
  }

  private coverage(sourceId: string) {
    const mine = this.receipts.get(sourceId);
    if (!mine) return json(404, { error: 'not_found', message: 'Unknown source' });
    const n = mine.size;
    const c: Coverage = {
      total: n,
      on_box: n,
      backed_up: Math.floor(n * this.coverageRatio.backed_up),
      verified: Math.floor(n * this.coverageRatio.verified),
      as_of: new Date().toISOString(),
    };
    return json(200, c);
  }

  private create(h: Headers) {
    const sourceId = h.get('OneMind-Source-Id') ?? '';
    if (!this.receipts.has(sourceId)) return json(404, { error: 'not_found', message: 'Unknown source' });
    const length = Number(h.get('Upload-Length'));
    const hash = h.get('OneMind-Content-Hash') ?? '';
    if (!Number.isSafeInteger(length) || length <= 0 || !/^sha256:[0-9a-f]{64}$/.test(hash))
      return json(400, { error: 'bad_request', message: 'Upload-Length and OneMind-Content-Hash are required' });
    const id = `upl_${++this.seq}`;
    this.uploads.set(id, { id, sourceId, clientKey: h.get('OneMind-Client-Key') ?? '', hash, length, offset: 0, hasher: sha256.create(), complete: false });
    this.stats.uploadsCreated++;
    return new Response(null, { status: 201, headers: { Location: `/v1/photos/uploads/${id}`, 'Upload-Offset': '0' } });
  }

  private patch(up: Upload, h: Headers, body: unknown) {
    this.stats.patches++;
    if (this.faults.failPatches) {
      this.faults.failPatches--;
      throw new TypeError('Network request failed');
    }
    if (up.complete) return json(409, { error: 'conflict', message: 'Upload already complete' });
    const at = Number(h.get('Upload-Offset'));
    if (at !== up.offset) return new Response(JSON.stringify({ error: 'conflict', message: 'Offset mismatch' }), { status: 409, headers: offsetHeaders(up) });
    let bytes = body instanceof Uint8Array ? body : new Uint8Array(0);
    if (up.offset + bytes.length > up.length) return json(400, { error: 'bad_request', message: 'More bytes than Upload-Length' });
    const cut = this.faults.cutNextPatchAfter;
    if (cut !== undefined) {
      this.faults.cutNextPatchAfter = undefined;
      bytes = bytes.subarray(0, Math.min(cut, bytes.length));
      this.take(up, bytes);
      throw new TypeError('Network request failed (connection dropped)');
    }
    this.take(up, bytes);
    const last = h.get('Upload-Complete') === '?1';
    if (!last) return new Response(null, { status: 204, headers: offsetHeaders(up) });
    if (up.offset !== up.length) return new Response(JSON.stringify({ error: 'conflict', message: 'Upload is short' }), { status: 409, headers: offsetHeaders(up) });
    const got = `sha256:${bytesToHex(up.hasher.digest())}`;
    up.complete = true;
    this.uploads.delete(up.id);
    if (got !== up.hash) return json(409, { error: 'conflict', message: 'The bytes do not match the declared hash' });
    const mine = this.receipts.get(up.sourceId)!;
    const deduped = new Set(mine.values()).has(got);
    mine.set(up.clientKey, got);
    if (!this.blobs.has(got)) {
      this.blobs.add(got);
      this.stats.storedBlobs++;
    }
    this.stats.uploadsCompleted++;
    return json(200, { client_key: up.clientKey, hash: got, deduped });
  }

  private take(up: Upload, bytes: Uint8Array) {
    up.hasher.update(bytes);
    up.offset += bytes.length;
    this.stats.bytesReceived += bytes.length;
  }
}

function offsetHeaders(up: Upload): Record<string, string> {
  return { 'Upload-Offset': String(up.offset), 'Upload-Complete': up.complete ? '?1' : '?0', 'Upload-Length': String(up.length) };
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}
