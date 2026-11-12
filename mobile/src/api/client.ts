// SPDX-License-Identifier: Apache-2.0
// Copied from dashboard/src/api/client.ts (feat/gwmcp, commit 951470f) so the phone app and the
// dashboard speak the same contract types. Keep the two in sync; mobile changes noted inline.
import {
  ApiError,
  type Action,
  type ActionRequest,
  type ApiErrorBody,
  type CatalogApp,
  type Instance,
  type NodeRecord,
} from './types';

/**
 * Everything the dashboard is allowed to ask the hub. One method per §3 route,
 * nothing else (contract §5: "it calls only the §3 API").
 */
export interface OneMindApi {
  healthz(): Promise<{ ok: boolean }>;
  instance(): Promise<Instance>;
  nodes(): Promise<NodeRecord[]>;
  node(nodeId: string): Promise<NodeRecord>;
  apps(): Promise<CatalogApp[]>;
  createAction(req: ActionRequest): Promise<Action>;
  actions(): Promise<Action[]>;
  action(id: string): Promise<Action>;
  approve(id: string): Promise<Action>;
  deny(id: string): Promise<Action>;
  /** Hub clock minus browser clock (ms), learned from responses; undefined until known. */
  hubOffsetMs(): number | undefined;
}

const KNOWN_CODES = new Set([
  'permission_denied',
  'stale_precondition',
  'expired',
  'conflict',
  'outcome_unknown',
  'not_found',
  'unauthenticated',
]);

function isErrorBody(v: unknown): v is ApiErrorBody {
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof (v as ApiErrorBody).error === 'string' &&
    KNOWN_CODES.has((v as ApiErrorBody).error)
  );
}

/**
 * Mobile addition: trim, drop trailing slashes, and require an absolute http(s) URL.
 * Throws a plain Error with a user-facing message otherwise.
 */
export function normalizeHubUrl(raw: string): string {
  const v = raw.trim().replace(/\/+$/, '');
  let u: URL;
  try {
    u = new URL(v);
  } catch {
    throw new Error('Enter the hub address, for example https://hub.example:8080');
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error('The hub address must start with http:// or https://');
  return v;
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

/** Real client: talks to the gateway over HTTP with a bearer token. */
export class HttpApi implements OneMindApi {
  private readonly base: string;
  private readonly token: string;
  private readonly fetchFn: FetchLike;
  private readonly timeoutMs: number;
  private offsetMs: number | undefined;

  // Mobile change: the hub URL is required (a phone has no same-origin hub), and
  // every request has a timeout, because a phone off the home network otherwise
  // waits for the OS TCP timeout (a minute or more) on an unreachable LAN address.
  constructor(opts: { token: string; baseUrl: string; fetchFn?: FetchLike; timeoutMs?: number }) {
    this.base = normalizeHubUrl(opts.baseUrl);
    this.token = opts.token;
    this.fetchFn = opts.fetchFn ?? ((input, init) => fetch(input, init));
    this.timeoutMs = opts.timeoutMs ?? 10_000;
  }

  /**
   * `shape` is what a 2xx body must be. Anything else (an HTML page from a proxy
   * or SPA fallback, an empty body, the wrong JSON type) is an error, not data.
   */
  private async req<T>(method: string, path: string, body?: unknown, shape: 'object' | 'array' = 'object'): Promise<T> {
    let res: Response;
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
    const timer = ctl ? setTimeout(() => ctl.abort(), this.timeoutMs) : undefined;
    try {
      res = await this.fetchFn(this.base + path, {
        signal: ctl?.signal,
        method,
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${this.token}`,
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      if (ctl?.signal.aborted) throw new ApiError(0, 'network', `The hub did not answer within ${this.timeoutMs / 1000} s`);
      throw new ApiError(0, 'network', e instanceof Error ? e.message : 'Network error');
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
    // The hub stamps last_seen with its own clock; the Date header lets the UI
    // age it on that clock instead of the browser's (1 s resolution is enough
    // for the 30 s / 120 s thresholds).
    const hubDate = Date.parse(res.headers.get('Date') ?? '');
    if (!Number.isNaN(hubDate)) this.offsetMs = hubDate - Date.now();
    const text = await res.text();
    let data: unknown = undefined;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = undefined;
      }
    }
    if (!res.ok) {
      if (isErrorBody(data)) throw new ApiError(res.status, data.error, data.message);
      const code = res.status === 401 ? 'unauthenticated' : res.status === 404 ? 'not_found' : 'unknown';
      throw new ApiError(res.status, code, `HTTP ${res.status}`);
    }
    if (res.status === 204) return undefined as T;
    const valid =
      shape === 'array' ? Array.isArray(data) : typeof data === 'object' && data !== null && !Array.isArray(data);
    if (!valid) throw new ApiError(res.status, 'unknown', 'Unexpected response from the hub');
    return data as T;
  }

  hubOffsetMs() {
    return this.offsetMs;
  }
  healthz() {
    return this.req<{ ok: boolean }>('GET', '/healthz');
  }
  instance() {
    return this.req<Instance>('GET', '/v1/instance');
  }
  nodes() {
    return this.req<NodeRecord[]>('GET', '/v1/nodes', undefined, 'array');
  }
  node(nodeId: string) {
    return this.req<NodeRecord>('GET', `/v1/nodes/${encodeURIComponent(nodeId)}`);
  }
  apps() {
    return this.req<CatalogApp[]>('GET', '/v1/apps', undefined, 'array');
  }
  createAction(req: ActionRequest) {
    return this.req<Action>('POST', '/v1/actions', req);
  }
  actions() {
    return this.req<Action[]>('GET', '/v1/actions', undefined, 'array');
  }
  action(id: string) {
    return this.req<Action>('GET', `/v1/actions/${encodeURIComponent(id)}`);
  }
  approve(id: string) {
    return this.req<Action>('POST', `/v1/actions/${encodeURIComponent(id)}/approve`);
  }
  deny(id: string) {
    return this.req<Action>('POST', `/v1/actions/${encodeURIComponent(id)}/deny`);
  }
}
