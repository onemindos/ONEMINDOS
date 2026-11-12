// SPDX-License-Identifier: Apache-2.0
// The hand-written transport over the generated types (SDK.md §3): auth, retries with one
// idempotency key per logical call, approve read-back, typed errors, the hub clock offset.

import type { components } from "./gen/schema.js";
import { AmbiguousResultError, errorFor, NetworkError, OneMindError, UnexpectedResponseError } from "./errors.js";
import { EventsApi } from "./events.js";

export type Instance = components["schemas"]["Instance"];
export type Node = components["schemas"]["Node"];
export type CatalogApp = components["schemas"]["CatalogApp"];
export type Action = components["schemas"]["Action"];
export type AuditRecord = components["schemas"]["AuditRecord"];
export type AuditVerify = components["schemas"]["AuditVerify"];

export const SDK_VERSION = "0.1.0";
export const TERMINAL_STATES = new Set(["succeeded", "failed", "cancelled", "expired", "outcome_unknown"]);

/** Supplies the bearer token; onUnauthenticated() may refresh it once after a 401. */
export interface TokenProvider {
  token(): Promise<string> | string;
  onUnauthenticated?(): Promise<boolean>;
}

export function staticToken(token: string): TokenProvider {
  return { token: () => token };
}

export interface ClientOptions {
  baseUrl: string;
  token?: string | TokenProvider;
  /** Per-attempt timeout in ms (default 10 000). */
  timeoutMs?: number;
  /** Attempts for retryable calls (default 3). */
  retries?: number;
  /** The caller's principal id: lets a lost approve be confirmed by reading the action back. */
  principal?: string;
  fetch?: typeof fetch;
  /** Receives one-time warnings (plain http to a non-local hub). Default: console.warn. */
  onWarning?: (message: string) => void;
  /** Called after each attempt with method, path (no query), status (0 = network) and duration. */
  onTrace?: (method: string, path: string, status: number, ms: number) => void;
  sleep?: (ms: number) => Promise<void>;
}

export interface RequestActionInput {
  type: "app.install" | "app.remove" | (string & {});
  appId: string;
  /** Default 24 h, counted on the hub's clock. */
  expiresInMs?: number;
  /** Default: a fresh UUIDv4, reused on every retry of this one call. */
  idempotencyKey?: string;
}

export interface AuditQuery {
  afterSeq?: number;
  beforeSeq?: number;
  event?: string;
  principalId?: string;
  actionId?: string;
  since?: string;
  until?: string;
  limit?: number;
}

interface Req {
  method: "GET" | "POST";
  path: string;
  body?: unknown;
  retry?: boolean;
}

const RETRY_STATUSES = new Set([429, 502, 503, 504]);

export class OneMind {
  readonly baseUrl: string;
  readonly events: EventsApi;
  /** @internal */ readonly fetchImpl: typeof fetch;
  /** @internal */ readonly tokens: TokenProvider;
  /** @internal */ readonly sleep: (ms: number) => Promise<void>;
  private readonly timeoutMs: number;
  private readonly attempts: number;
  private readonly principal?: string;
  private readonly onWarning: (m: string) => void;
  private readonly onTrace?: ClientOptions["onTrace"];
  private warned = false;
  private offsetMs = 0;

  constructor(opts: ClientOptions) {
    const url = normalizeHubUrl(opts.baseUrl);
    this.baseUrl = url;
    this.tokens = typeof opts.token === "string" || opts.token === undefined ? staticToken(opts.token ?? "") : opts.token;
    this.timeoutMs = opts.timeoutMs ?? 10_000;
    this.attempts = Math.max(1, opts.retries ?? 3);
    this.principal = opts.principal;
    this.fetchImpl = opts.fetch ?? globalThis.fetch.bind(globalThis);
    this.onWarning = opts.onWarning ?? ((m) => console.warn(`onemind: warning: ${m}`));
    this.onTrace = opts.onTrace;
    this.sleep = opts.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.events = new EventsApi(this);
  }

  /** ONEMIND_HUB + ONEMIND_TOKEN, else ONEMIND_GATEWAY_URL + ONEMIND_AGENT_TOKEN (contract §11.2). */
  static fromEnv(env: Record<string, string | undefined> = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {}, extra: Partial<ClientOptions> = {}) {
    const hub = env.ONEMIND_HUB || env.ONEMIND_GATEWAY_URL;
    if (!hub) throw new Error("onemind: set ONEMIND_HUB (and ONEMIND_TOKEN) or ONEMIND_GATEWAY_URL");
    const token = env.ONEMIND_HUB ? env.ONEMIND_TOKEN : env.ONEMIND_AGENT_TOKEN;
    return new OneMind({ ...extra, baseUrl: hub, token: token ?? "" });
  }

  toString(): string {
    return `OneMind(hub=${this.baseUrl}, principal=${this.principal ?? "?"})`;
  }

  /** The hub's clock as last seen in a Date header. */
  hubNow(): number {
    return Date.now() + this.offsetMs;
  }

  hubOffsetMs(): number {
    return this.offsetMs;
  }

  // ---- operations ------------------------------------------------------------------------------
  async healthz(): Promise<boolean> {
    return ((await this.call<{ ok: boolean }>({ method: "GET", path: "/healthz" })) ?? { ok: false }).ok;
  }

  readonly instance = { get: () => this.call<Instance>({ method: "GET", path: "/v1/instance" }) };

  readonly nodes = {
    list: () => this.call<Node[]>({ method: "GET", path: "/v1/nodes" }),
    get: (id: string) => this.call<Node>({ method: "GET", path: `/v1/nodes/${encodeURIComponent(id)}` }),
  };

  readonly apps = {
    list: () => this.call<CatalogApp[]>({ method: "GET", path: "/v1/apps" }),
  };

  readonly actions = {
    /** actions.create: files the action in awaiting_approval; safe to retry (one idempotency key). */
    request: async (input: RequestActionInput): Promise<Action> => {
      await this.instance.get(); // learn the hub clock first
      const body = {
        type: input.type,
        params: { app_id: input.appId },
        idempotency_key: input.idempotencyKey ?? uuid4(),
        expires_at: new Date(this.hubNow() + (input.expiresInMs ?? 24 * 3600_000)).toISOString().replace(/\.\d{3}Z$/, "Z"),
      };
      return this.call<Action>({ method: "POST", path: "/v1/actions", body, retry: true });
    },
    list: () => this.call<Action[]>({ method: "GET", path: "/v1/actions" }),
    get: (id: string) => this.call<Action>({ method: "GET", path: `/v1/actions/${encodeURIComponent(id)}` }),
    approve: (id: string) => this.decide(id, "approve"),
    deny: (id: string) => this.decide(id, "deny"),
    /** Poll until the action is terminal (or the signal aborts). */
    wait: async (id: string, opts: { everyMs?: number; signal?: AbortSignal; onChange?: (a: Action) => void } = {}) => {
      let last = "";
      for (;;) {
        const a = await this.actions.get(id);
        if (a.state !== last) {
          last = a.state;
          opts.onChange?.(a);
        }
        if (TERMINAL_STATES.has(a.state) || opts.signal?.aborted) return a;
        await this.sleep(opts.everyMs ?? 2000);
      }
    },
  };

  readonly audit = {
    /** audit.events.list; `more` is true when the gateway sent Link rel="next". */
    list: async (q: AuditQuery = {}): Promise<{ records: AuditRecord[]; more: boolean }> => {
      const p = new URLSearchParams();
      const map: Record<string, unknown> = {
        after_seq: q.afterSeq, before_seq: q.beforeSeq, event: q.event, principal_id: q.principalId,
        action_id: q.actionId, since: q.since, until: q.until, limit: q.limit,
      };
      for (const [k, v] of Object.entries(map)) if (v !== undefined && v !== "") p.set(k, String(v));
      const qs = p.toString();
      const { body, headers } = await this.raw<AuditRecord[]>({ method: "GET", path: `/v1/audit/events${qs ? `?${qs}` : ""}`, retry: true });
      return { records: body, more: /rel="next"/.test(headers.get("link") ?? "") };
    },
    get: (seq: number) => this.call<AuditRecord>({ method: "GET", path: `/v1/audit/events/${seq}` }),
    verify: () => this.call<AuditVerify>({ method: "GET", path: "/v1/audit/verify" }),
  };

  // ---- transport ---------------------------------------------------------------------------------
  private async decide(id: string, verb: "approve" | "deny"): Promise<Action> {
    try {
      return await this.call<Action>({ method: "POST", path: `/v1/actions/${encodeURIComponent(id)}/${verb}` });
    } catch (e) {
      if (e instanceof OneMindError && e.status !== 0 && e.status < 500) throw e;
      let got: Action;
      try {
        got = await this.actions.get(id);
      } catch {
        throw new AmbiguousResultError(`${verb} may or may not have been applied; check the action`);
      }
      if (got.state !== "awaiting_approval" && this.principal && got.decided_by?.id === this.principal) return got;
      throw new AmbiguousResultError(`${verb} may or may not have been applied; the action is now ${got.state}`, got);
    }
  }

  /** One API call; returns the parsed JSON body. */
  async call<T>(r: Req): Promise<T> {
    return (await this.raw<T>({ ...r, retry: r.retry ?? r.method === "GET" })).body;
  }

  /** @internal */
  async authHeader(): Promise<Record<string, string>> {
    const t = await this.tokens.token();
    return t ? { Authorization: `Bearer ${t}` } : {};
  }

  /** @internal */
  checkTransport(): void {
    const u = new URL(this.baseUrl);
    if (u.protocol === "http:" && !["localhost", "127.0.0.1", "[::1]"].includes(u.hostname) && !this.warned) {
      this.warned = true;
      this.onWarning(`talking to ${u.host} over plain http: the token crosses the network unencrypted`);
    }
  }

  private async raw<T>(r: Req): Promise<{ body: T; headers: Headers }> {
    this.checkTransport();
    const attempts = r.retry ? this.attempts : 1;
    let refreshed = false;
    let last: unknown;
    for (let i = 0; i < attempts; i++) {
      if (i > 0) {
        const ra = last instanceof OneMindError ? last.retryAfterS : undefined;
        await this.sleep(ra ? ra * 1000 : Math.random() * Math.min(4000, 250 * 2 ** (i - 1)));
      }
      try {
        return await this.once<T>(r);
      } catch (e) {
        last = e;
        if (e instanceof OneMindError && e.status === 401 && !refreshed && this.tokens.onUnauthenticated) {
          refreshed = true;
          if (await this.tokens.onUnauthenticated()) {
            i--;
            continue;
          }
        }
        const retryable = e instanceof NetworkError || (e instanceof OneMindError && RETRY_STATUSES.has(e.status));
        if (!retryable) throw e;
      }
    }
    throw last;
  }

  private async once<T>(r: Req): Promise<{ body: T; headers: Headers }> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    const started = Date.now();
    const pathOnly = r.path.split("?")[0] ?? r.path;
    let res: Response;
    try {
      res = await this.fetchImpl(this.baseUrl + r.path, {
        method: r.method,
        headers: {
          Accept: "application/json",
          ...(r.body !== undefined ? { "Content-Type": "application/json" } : {}),
          ...(await this.authHeader()),
        },
        body: r.body !== undefined ? JSON.stringify(r.body) : undefined,
        signal: ctrl.signal,
      });
    } catch (e) {
      this.onTrace?.(r.method, pathOnly, 0, Date.now() - started);
      const timedOut = ctrl.signal.aborted;
      throw new NetworkError(timedOut ? "request timed out" : "could not reach the hub", timedOut);
    } finally {
      clearTimeout(timer);
    }
    this.onTrace?.(r.method, pathOnly, res.status, Date.now() - started);
    const date = res.headers.get("date");
    if (date && !Number.isNaN(Date.parse(date))) this.offsetMs = Date.parse(date) - Date.now();
    const text = await res.text();
    let json: unknown;
    try {
      json = text ? JSON.parse(text) : undefined;
    } catch {
      json = undefined;
    }
    if (!res.ok) {
      const b = json as { error?: string; message?: string; reason?: string; retry_after_s?: number } | undefined;
      const ra = Number(res.headers.get("retry-after")) || b?.retry_after_s;
      if (b && typeof b.error === "string") {
        throw errorFor(res.status, b.error, b.message ?? "", { reason: b.reason, retryAfterS: ra || undefined });
      }
      throw errorFor(res.status, res.status === 404 ? "not_found" : "unexpected_response",
        `HTTP ${res.status} without the OneMind error body`, { retryAfterS: ra || undefined });
    }
    if (json === undefined && res.status !== 204) {
      throw new UnexpectedResponseError(res.status, "unexpected_response", "the hub did not answer with JSON (a proxy in the way?)");
    }
    return { body: json as T, headers: res.headers };
  }
}

/** Absolute http(s) URL without a trailing slash; a bare host gets http:// (the mobile rule). */
export function normalizeHubUrl(input: string): string {
  let s = input.trim();
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(s)) s = `http://${s}`;
  const u = new URL(s);
  if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error(`onemind: hub URL must be http(s), got ${input}`);
  return `${u.protocol}//${u.host}${u.pathname.replace(/\/+$/, "")}`;
}

export function uuid4(): string {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  const b = new Uint8Array(16);
  c.getRandomValues(b);
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
