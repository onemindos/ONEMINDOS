// SPDX-License-Identifier: Apache-2.0
// The Files window's client for /v1/files/*. Paths are typed against the generated OpenAPI `paths`
// (a route renamed in core/ stops compiling here after `make -C sdk gen`); bodies use the generated
// `components` types. Responses are checked at the edge: the spec leaves most of them as `unknown`.
import { OneMind, OneMindError, PROTOCOL_HEADER, PROTOCOL_VERSION, type components, type paths } from '@onemind/sdk';
import { ApiError } from '../api/types';

const P = {
  roots: '/v1/files/roots',
  list: '/v1/files/list',
  preview: '/v1/files/preview',
  download: '/v1/files/download',
  ops: '/v1/files/ops',
  trash: '/v1/files/trash',
  trashEmpty: '/v1/files/trash/empty',
  grants: '/v1/files/grants',
  grant: '/v1/files/grants/{grant_id}',
  requests: '/v1/files/requests',
  approve: '/v1/files/requests/{request_id}/approve',
  deny: '/v1/files/requests/{request_id}/deny',
  cancel: '/v1/files/requests/{request_id}/cancel',
  uploads: '/v1/files/uploads',
  versions: '/v1/files/versions',
  quotas: '/v1/files/quotas',
  quota: '/v1/files/quotas/{person_id}',
} as const satisfies Record<string, keyof paths>;

const SHARE = { targets: '/v1/share/targets', send: '/v1/share' } as const satisfies Record<string, keyof paths>;

type Json = Record<string, unknown>;
export type GrantBody = components['schemas']['GrantBody'];
type RestoreVersionOp = components['schemas']['RestoreVersionOp'];
/** An app that accepts a shared object of one type (GET /v1/share/targets). */
export type ShareTarget = components['schemas']['ShareTarget'];
export type ShareTargets = components['schemas']['ShareTargetsOut'];
export type ShareBody = components['schemas']['ShareIn'];
export type ShareResult = components['schemas']['ShareOut'];

export interface FileRoot { root: string; kind: string; name: string; path: string; access: string; writable: boolean; used_bytes: number | null; quota_bytes: number | null; free_bytes: number | null }
export interface Entry { name: string; path: string; type: 'file' | 'dir' | string; size: number | null; mtime: string; mime?: string }
export interface TrashItem { id: string; trash: 'home' | 'shared'; root: string; path: string; name: string; type: string; size: number; trashed_at: string; purge_at: string }
export interface Grant { id: string; subject: { kind: string; id: string }; slot: string | null; root: string; path: string; access: string; revoked_at: string | null }
export interface FileRequest { id: string; type: string; plan: { summary?: string }; risk: string; state: string; reason: string | null; requested_by: { id: string; kind: string }; expires_at: string; plan_sha256: string; deny_reason: string | null }
/** An earlier copy of a file in the box's local snapshots (BAK-04). Same disk as the file: not a backup. */
export type FileVersion = components['schemas']['FileVersion'];
export type FileVersions = Pick<components['schemas']['FileVersions'], 'enabled' | 'exists' | 'versions'>;
/** One space's limit: a person's home, or the shared space (person_id null). limit_bytes null means no limit.
 *  Hand-written because GET/PUT /v1/files/quotas declare no response_model, so the spec has no schema to
 *  generate from (the rows are checked at the edge below). Core follow-up: #1278. */
export interface Quota { person_id: string | null; root: string; limit_bytes: number | null; used_bytes: number }
export interface Preview { mime: string; kind: string; size: number; inline_safe: boolean; image?: { width: number; height: number } | null; text?: { excerpt: string; truncated: boolean } }

function obj(v: unknown, what: string): Json {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error(`The hub returned an invalid ${what}.`);
  return v as Json;
}
function list<T>(v: unknown, what: string, ok: (j: Json) => boolean): T[] {
  if (!Array.isArray(v)) throw new Error(`The hub returned an invalid ${what} list.`);
  return v.map((x) => { const j = obj(x, what); if (!ok(j)) throw new Error(`The hub returned an invalid ${what}.`); return j as unknown as T; });
}
const str = (v: unknown) => typeof v === 'string';
const fill = (path: string, key: string, id: string) => path.replace(`{${key}}`, encodeURIComponent(id));

export function toApiError(e: unknown): unknown {
  if (e instanceof OneMindError) return new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : e.status === 409 ? 'stale_precondition' : 'unknown', e.message, e.reason);
  return e;
}
async function failure(res: Response): Promise<ApiError> {
  let b: { error?: string; message?: string; reason?: string } = {};
  try { b = await res.json(); } catch { /* not JSON */ }
  return new ApiError(res.status, res.status === 401 ? 'unauthenticated' : res.status === 403 ? 'permission_denied' : res.status === 409 ? 'stale_precondition' : 'unknown', b.message ?? `HTTP ${res.status}`, b.reason);
}
const q = (params: Record<string, string | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) s.set(k, v);
  return `?${s}`;
};
/** tus Upload-Metadata value: base64 of the UTF-8 bytes. */
const b64 = (s: string) => { let bin = ''; for (const b of new TextEncoder().encode(s)) bin += String.fromCharCode(b); return btoa(bin); };
const CHUNK = 256 * 1024; // the gateway's default maximum HTTP request body
function uploadOffset(header: string | null, min: number, max: number): number {
  const value = header !== null && /^\d+$/.test(header) ? Number(header) : NaN;
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw new ApiError(409, 'stale_precondition', 'The hub returned an invalid upload offset.');
  }
  return value;
}

export class FilesApi {
  private readonly sdk: OneMind;
  constructor(private readonly token: string, private readonly fetchImpl: typeof fetch = (...a) => fetch(...a)) {
    this.sdk = new OneMind({ baseUrl: window.location.origin, token, retries: 1, fetch: (...a) => this.fetchImpl(...a) });
  }
  private async get(path: string) { try { return await this.sdk.call<unknown>({ method: 'GET', path }); } catch (e) { throw toApiError(e); } }
  private async post(path: string, body: unknown, key?: string) {
    try { return await this.sdk.call<unknown>({ method: 'POST', path, body, retry: key !== undefined, headers: key ? { 'Idempotency-Key': key } : undefined }); } catch (e) { throw toApiError(e); }
  }
  private auth = (extra: Record<string, string> = {}) => ({ Authorization: `Bearer ${this.token}`, [PROTOCOL_HEADER]: String(PROTOCOL_VERSION), ...extra });

  async roots() { return list<FileRoot>(await this.get(P.roots), 'space', (j) => str(j.root) && str(j.name)); }
  async list(root: string, path: string) { return list<Entry>(await this.get(P.list + q({ root, path, limit: '500' })), 'entry', (j) => str(j.name) && str(j.path) && str(j.type)); }
  async preview(root: string, path: string) { return obj(await this.get(P.preview + q({ root, path })), 'preview') as unknown as Preview; }
  /** Owner only: every space's limit and use. */
  async quotas() { return list<Quota>(await this.get(P.quotas), 'quota', (j) => str(j.root) && typeof j.used_bytes === 'number'); }
  /** Owner only: set a person's limit in bytes, or null for no limit. */
  async setQuota(personId: string, limitBytes: number | null) {
    try { return obj(await this.sdk.call<unknown>({ method: 'PUT', path: fill(P.quota, 'person_id', personId), body: { limit_bytes: limitBytes } }), 'quota') as unknown as Quota; } catch (e) { throw toApiError(e); }
  }
  async mkdir(root: string, path: string) { await this.post(P.ops, { op: 'mkdir', root, path }); }
  async trash(root: string, path: string) { await this.post(P.ops, { op: 'trash', root, path }); }
  async versions(root: string, path: string): Promise<FileVersions> {
    const j = obj(await this.get(P.versions + q({ root, path })), 'version list');
    const versions = list<FileVersion>(j.versions, 'version', (v) => str(v.version) && str(v.taken_at) && typeof v.size === 'number');
    return { enabled: j.enabled === true, exists: j.exists === true, versions };
  }
  /** Copies an earlier version back as a new file (beside the current one when its name is taken); never overwrites. */
  async restoreVersion(root: string, path: string, version: string): Promise<Entry> {
    const body: RestoreVersionOp = { op: 'restore_version', root, path, version };
    const j = obj(await this.post(P.ops, body), 'restored file');
    if (!str(j.path) || !str(j.name)) throw new Error('The hub returned an invalid restored file.');
    return j as unknown as Entry;
  }
  async restore(trashId: string) { await this.post(P.ops, { op: 'restore_trash', trash_id: trashId }); }
  /** The "Send to" list for one type: switched-on apps you can see that accept it and hold its data grant. */
  async shareTargets(type: string) {
    const v = obj(await this.get(SHARE.targets + q({ type })), 'share targets') as unknown as ShareTargets;
    return list<ShareTarget>(v.targets, 'share target', (j) => str(j.app_id) && str(j.name) && Array.isArray(j.verbs));
  }
  /** Hand one object to one app: a reference, never the content. A repeated key replays the first share. */
  async shareSend(body: ShareBody, key: string) {
    return obj(await this.post(SHARE.send, body, key), 'share') as unknown as ShareResult;
  }
  async trashList(which: 'home' | 'shared') { return list<TrashItem>(await this.get(P.trash + q({ trash: which, limit: '500' })), 'trash item', (j) => str(j.id) && str(j.name)); }
  async grants() { return list<Grant>(await this.get(P.grants), 'grant', (j) => str(j.id) && str(j.root)); }
  async requests() { return list<FileRequest>(await this.get(P.requests), 'request', (j) => str(j.id) && str(j.state) && str(j.plan_sha256)); }
  /** Files an approval request (approve stays false: a person decides it in the list). One key per logical request. */
  async requestGrant(body: Omit<GrantBody, 'approve'>, key: string) { return this.post(P.grants, { ...body, approve: false }, key); }
  async requestTrashEmpty(which: 'home' | 'shared', key: string) { return this.post(P.trashEmpty, { trash: which, approve: false }, key); }
  /** Approve exactly the plan that was shown (409 plan_changed when it moved). */
  async approve(r: FileRequest) { return this.post(fill(P.approve, 'request_id', r.id), { plan_sha256: r.plan_sha256 }); }
  async deny(id: string) { return this.post(fill(P.deny, 'request_id', id), {}); }
  async cancel(id: string) { return this.post(fill(P.cancel, 'request_id', id), undefined); }
  async revoke(id: string) {
    const res = await this.fetchImpl(fill(P.grant, 'grant_id', id), { method: 'DELETE', headers: this.auth() });
    if (!res.ok) throw await failure(res);
  }

  /** The file's bytes (inline=true for a browser-safe type), for a download or an image preview. */
  async fetchBlob(root: string, path: string, inline = false): Promise<Blob> {
    const res = await this.fetchImpl(P.download + q({ root, path, inline: inline ? 'true' : undefined }), { headers: this.auth() });
    if (!res.ok) throw await failure(res);
    return res.blob();
  }

  /** Resumable upload (tus 1.0.0): create, then PATCH in chunks; a dropped chunk asks the hub for its offset and goes on. */
  async upload(file: File, root: string, dir: string, onProgress: (done: number) => void, overwrite = false): Promise<string> {
    const tus = { 'Tus-Resumable': '1.0.0' };
    const meta = [`filename ${b64(file.name)}`, `root ${b64(root)}`, `path ${b64(dir)}`, ...(overwrite ? [`overwrite ${b64('1')}`] : [])].join(',');
    const made = await this.fetchImpl(P.uploads, { method: 'POST', headers: this.auth({ ...tus, 'Upload-Length': String(file.size), 'Upload-Metadata': meta }) });
    if (!made.ok) throw await failure(made);
    const location = new URL(made.headers.get('Location') ?? '', window.location.origin);
    if (location.origin !== window.location.origin || !/^\/v1\/files\/uploads\/upl_[0-9A-Z]+$/.test(location.pathname)) throw new Error('The hub returned an invalid upload location.');
    const where = location.pathname;
    let offset = uploadOffset(made.headers.get('Upload-Offset') ?? '0', 0, file.size);
    let failures = 0;
    while (offset < file.size) {
      const end = Math.min(offset + CHUNK, file.size);
      try {
        const res = await this.fetchImpl(where, { method: 'PATCH', headers: this.auth({ ...tus, 'Upload-Offset': String(offset), 'Content-Type': 'application/offset+octet-stream' }), body: file.slice(offset, end) });
        if (res.status === 429 && failures++ < 3) {
          const seconds = Math.max(1, Math.min(60, Number(res.headers.get('Retry-After')) || 1));
          await new Promise((resolve) => setTimeout(resolve, seconds * 1000));
          continue;
        }
        if (!res.ok) throw await failure(res);
        offset = uploadOffset(res.headers.get('Upload-Offset'), offset + 1, end);
        failures = 0;
        onProgress(offset);
      } catch (e) {
        if (e instanceof ApiError || ++failures > 3) throw e;
        const head = await this.fetchImpl(where, { method: 'HEAD', headers: this.auth(tus) });
        if (head.ok) offset = uploadOffset(head.headers.get('Upload-Offset'), offset, end);
      }
    }
    return where;
  }

  async completedUpload(location: string) {
    if (!/^\/v1\/files\/uploads\/upl_[0-9A-Z]+$/.test(location)) throw new Error('Invalid upload location.');
    const row = obj(await this.get(location), 'upload');
    if (row.state !== 'done' || typeof row.id !== 'string' || location !== `/v1/files/uploads/${row.id}`
      || typeof row.length !== 'number' || !Number.isSafeInteger(row.length) || row.length < 1 || typeof row.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(row.sha256)) {
      throw new Error('The hub has not verified the whole file.');
    }
    return { upload_id: row.id, sha256: row.sha256, size_bytes: row.length };
  }
}

export function human(n: number | null | undefined): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0, v = n;
  while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
  return `${i === 0 ? v : v.toFixed(v < 10 ? 1 : 0)} ${u[i]}`;
}
