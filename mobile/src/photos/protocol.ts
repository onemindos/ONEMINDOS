// SPDX-License-Identifier: Apache-2.0
// Client for the interim Photos backup API (mobile/docs/photos-backup-api.md). The shapes follow
// the photos study's proposal for contract §12-p; nothing is binding until that PR merges, so
// every route and header lives in this one file.
import type { FetchLike } from '../api/client';
import { ApiError } from '../api/types';

/** Value of `Upload-Draft-Interop-Version` (IETF resumable uploads draft). Check against PH-3. */
export const UPLOAD_INTEROP_VERSION = '7';

export type Platform = 'ios' | 'android' | 'other';

export interface PhotoSource {
  id: string;
  client_id: string;
  name: string;
  platform: Platform;
}

/** One item to check. `hash` is `sha256:<64 hex>` of the exact bytes the phone would send. */
export interface CheckItem {
  client_key: string;
  size: number;
  hash: string;
}

export interface CheckAnswer {
  client_key: string;
  status: 'have' | 'need';
}

export interface UploadMeta {
  sourceId: string;
  clientKey: string;
  hash: string;
  size: number;
  fileName: string;
  /** Phone creation time, ms since epoch: a fallback when the file has no capture date. */
  createdAt?: number;
}

export interface UploadReceipt {
  client_key: string;
  hash: string;
  /** True when the box already had these bytes for this person's phone and kept no new copy. */
  deduped: boolean;
}

export interface UploadOffset {
  offset: number;
  complete: boolean;
}

/** B1: what the box can say about this phone's items. Only `verified` may ever free phone space. */
export interface Coverage {
  total: number;
  on_box: number;
  backed_up: number;
  verified: number;
  as_of: string;
}

export interface PhotosApi {
  readonly host: string;
  registerSource(req: { client_id: string; name: string; platform: Platform }): Promise<PhotoSource>;
  check(sourceId: string, items: CheckItem[]): Promise<CheckAnswer[]>;
  /** Creates an empty resumable upload and returns its absolute URL. */
  createUpload(meta: UploadMeta): Promise<string>;
  /** Asks the box how many bytes of this upload it holds. */
  uploadOffset(url: string): Promise<UploadOffset>;
  /** Appends bytes at `offset`. With `last`, the box finishes the upload and returns its receipt. */
  appendChunk(url: string, offset: number, bytes: Uint8Array, last: boolean): Promise<{ offset: number; receipt?: UploadReceipt }>;
  coverage(sourceId: string): Promise<Coverage>;
}

export const MAX_CHECK = 500;

function codeFor(status: number, body: unknown): ApiError['code'] {
  const e = typeof body === 'object' && body !== null ? (body as { error?: unknown }).error : undefined;
  if (e === 'permission_denied' || e === 'conflict' || e === 'not_found' || e === 'unauthenticated') return e;
  if (status === 401) return 'unauthenticated';
  if (status === 403) return 'permission_denied';
  if (status === 404 || status === 410) return 'not_found';
  if (status === 409) return 'conflict';
  return 'unknown';
}

function header(res: Response, name: string): string | null {
  return res.headers.get(name);
}

function parseOffset(res: Response): number {
  const n = Number(header(res, 'Upload-Offset'));
  if (!Number.isSafeInteger(n) || n < 0) throw new ApiError(res.status, 'unknown', 'The box sent no valid Upload-Offset');
  return n;
}

/**
 * HTTPS only (B3, DN-1): photos never travel over plain HTTP, and the token is only ever sent
 * to the box's own origin (an upload URL on another origin is refused).
 */
export class HttpPhotosApi implements PhotosApi {
  readonly host: string;
  private readonly origin: string;
  private readonly base: string;
  private readonly token: string;
  private readonly fetchFn: FetchLike;
  private readonly timeoutMs: number;

  constructor(opts: { baseUrl: string; token: string; fetchFn?: FetchLike; timeoutMs?: number }) {
    const u = new URL(opts.baseUrl.trim().replace(/\/+$/, ''));
    if (u.protocol !== 'https:') throw new ApiError(0, 'unknown', 'Photo backup needs an HTTPS address for your OneMind');
    this.origin = u.origin;
    this.host = u.host;
    this.base = u.origin + u.pathname.replace(/\/+$/, '');
    this.token = opts.token;
    this.fetchFn = opts.fetchFn ?? ((input, init) => fetch(input, init));
    this.timeoutMs = opts.timeoutMs ?? 60_000;
  }

  private resolve(url: string): string {
    const u = new URL(url, this.base + '/');
    if (u.origin !== this.origin) throw new ApiError(0, 'unknown', 'The box gave an upload address on another server; refused');
    return u.toString();
  }

  private async send(method: string, url: string, headers: Record<string, string>, body?: string | Uint8Array): Promise<Response> {
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
    const timer = ctl ? setTimeout(() => ctl.abort(), this.timeoutMs) : undefined;
    let res: Response;
    try {
      res = await this.fetchFn(url, {
        method,
        signal: ctl?.signal,
        headers: { Authorization: `Bearer ${this.token}`, ...headers },
        body: body as BodyInit | undefined,
      });
    } catch (e) {
      if (ctl?.signal.aborted) throw new ApiError(0, 'network', `The box did not answer within ${this.timeoutMs / 1000} s`);
      throw new ApiError(0, 'network', e instanceof Error ? e.message : 'Network error');
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      let data: unknown;
      try {
        data = text ? JSON.parse(text) : undefined;
      } catch {
        data = undefined;
      }
      const msg = typeof data === 'object' && data && typeof (data as { message?: unknown }).message === 'string' ? (data as { message: string }).message : `HTTP ${res.status}`;
      throw new ApiError(res.status, codeFor(res.status, data), msg);
    }
    return res;
  }

  private async json<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await this.send(
      method,
      this.base + path,
      { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body !== undefined ? JSON.stringify(body) : undefined,
    );
    const text = await res.text();
    try {
      const v = JSON.parse(text) as unknown;
      if (typeof v === 'object' && v !== null) return v as T;
    } catch {
      /* fall through */
    }
    throw new ApiError(res.status, 'unknown', 'Unexpected response from the box');
  }

  registerSource(req: { client_id: string; name: string; platform: Platform }) {
    return this.json<PhotoSource>('POST', '/v1/photos/sources', req);
  }

  async check(sourceId: string, items: CheckItem[]) {
    if (items.length > MAX_CHECK) throw new Error(`check takes at most ${MAX_CHECK} items`);
    const r = await this.json<{ items?: CheckAnswer[] }>('POST', `/v1/photos/sources/${encodeURIComponent(sourceId)}/check`, { items });
    if (!Array.isArray(r.items)) throw new ApiError(200, 'unknown', 'Unexpected response from the box');
    return r.items;
  }

  async createUpload(m: UploadMeta) {
    const res = await this.send('POST', this.base + '/v1/photos/uploads', {
      'Upload-Draft-Interop-Version': UPLOAD_INTEROP_VERSION,
      'Upload-Complete': '?0',
      'Upload-Length': String(m.size),
      'OneMind-Source-Id': m.sourceId,
      'OneMind-Client-Key': m.clientKey,
      'OneMind-Content-Hash': m.hash,
      'OneMind-File-Name': encodeURIComponent(m.fileName),
      ...(m.createdAt ? { 'OneMind-Created-At': new Date(m.createdAt).toISOString() } : {}),
    });
    const loc = header(res, 'Location');
    if (!loc) throw new ApiError(res.status, 'unknown', 'The box did not return an upload address');
    return this.resolve(loc);
  }

  async uploadOffset(url: string) {
    const res = await this.send('HEAD', this.resolve(url), { 'Upload-Draft-Interop-Version': UPLOAD_INTEROP_VERSION });
    return { offset: parseOffset(res), complete: header(res, 'Upload-Complete') === '?1' };
  }

  async appendChunk(url: string, offset: number, bytes: Uint8Array, last: boolean) {
    const res = await this.send(
      'PATCH',
      this.resolve(url),
      {
        'Upload-Draft-Interop-Version': UPLOAD_INTEROP_VERSION,
        'Upload-Offset': String(offset),
        'Upload-Complete': last ? '?1' : '?0',
        'Content-Type': 'application/partial-upload',
      },
      bytes,
    );
    if (!last) return { offset: parseOffset(res) };
    const text = await res.text();
    let receipt: UploadReceipt | undefined;
    try {
      receipt = JSON.parse(text) as UploadReceipt;
    } catch {
      receipt = undefined;
    }
    if (!receipt || typeof receipt.hash !== 'string') throw new ApiError(res.status, 'unknown', 'The box finished the upload without a receipt');
    return { offset: offset + bytes.length, receipt };
  }

  coverage(sourceId: string) {
    return this.json<Coverage>('GET', `/v1/photos/sources/${encodeURIComponent(sourceId)}/coverage`);
  }
}
