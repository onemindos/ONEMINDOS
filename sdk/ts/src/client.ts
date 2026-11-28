// SPDX-License-Identifier: Apache-2.0
// The hand-written transport over the generated types (SDK.md §3): auth, retries with one
// idempotency key per logical call, approve read-back, typed errors, the hub clock offset.

import type { components } from "./gen/schema.js";
import { AmbiguousResultError, errorFor, NetworkError, OneMindError, UnexpectedResponseError } from "./errors.js";
import { EventsApi } from "./events.js";
import { caFetch } from "./nodeca.js";
import { PROTOCOL_HEADER, PROTOCOL_VERSION } from "./protocol.js";

export type Instance = components["schemas"]["Instance"];
export type StatusView = components["schemas"]["StatusView"];
export type Node = components["schemas"]["Node"];
export type CatalogApp = components["schemas"]["CatalogApp"];
export type Action = components["schemas"]["Action"];
export type AuditRecord = components["schemas"]["AuditRecord"];
export type AuditVerify = components["schemas"]["AuditVerify"];
/** This box's interfaces, gateway, DNS and listening ports, read only (`/v1/network`, owner only). */
export type NetworkView = components["schemas"]["NetworkView"];
/** What to change on a wired interface (`PUT /v1/network/{iface}`, P-08): a fixed IPv4 setup or back to DHCP. */
export type NetworkConfigBody = components["schemas"]["NetworkConfigBody"];
/** The approval and reachability check for a pending wired network change. */
export type NetworkConfirmBody = components["schemas"]["NetworkConfirmBody"];
/** The answer of `POST /v1/network/{iface}/confirm`. */
export type NetworkConfirm = components["schemas"]["NetworkConfirm"];
/** The box's own screen as the full-screen dashboard (`/v1/instance/kiosk`, owner only). */
export type KioskState = components["schemas"]["KioskState"];

/** One name an owner asked for under their own domain (`<app>.<domain>`); `approved` is a recorded decision only. */
export interface DomainHost {
  hostname: string;
  app_id: string;
  state: "requested" | "approved" | string;
  requested_by: string | null;
  approved_by: string | null;
  updated_at: string | null;
  public: boolean;
}
/** A registered domain, its proof record (a TXT record to add at the DNS provider) and its names. */
export interface DomainView {
  domain: string;
  verified: boolean;
  verified_at: string | null;
  proof: { type: "TXT"; name: string; value: string };
  hosts: DomainHost[];
}
/** `GET /v1/domains`: `enabled` is false until the owner turns bring-your-own-domain on for the box. */
export interface DomainsSummary {
  enabled: boolean;
  acme: { account_thumbprint: string | null; issuance: string };
  domains: DomainView[];
}

/** The box's live firewall, explained in plain words, read only (`/v1/network/firewall`, owner only). */
export type FirewallView = components["schemas"]["FirewallView"];
/** One port the owner opened (P-09 part 2): pending until confirmed, then kept; a pending rule reverts at `expires_at`. */
export type AllowRule = components["schemas"]["AllowRule"];
/** What to ask for: one port, one protocol, the home network (`lan`) or the mesh. The internet is not an option. */
export type AllowRequest = components["schemas"]["AllowRequest"];
/** The caller's own Home document (UMB-P07, `/v1/me/home`). */
export type HomeView = components["schemas"]["HomeView"];
export type HomeBody = components["schemas"]["HomeBody"];
/** A Home document with the validator to send back on the next save. */
export interface HomeWithEtag {
  home: HomeView;
  etag: string;
}

/** A person's notification routing document (GET /v1/notifications/preferences) with the ETag to send back. */
export interface NotificationPreferencesWithEtag {
  prefs: Record<string, unknown>;
  etag: string;
}

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
  /** An absolute RFC 3339 expiry; wins over expiresInMs. A caller replaying one logical request by
   * hand passes the same value, because the hub compares it (to the second) with the first call. */
  expiresAt?: string;
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
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
  body?: unknown;
  retry?: boolean;
  redirect?: RequestRedirect;
  headers?: Record<string, string>;
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
  /** expires_at fixed per idempotency key: the hub compares the whole body on a replay, so a retry
   *  that recomputed it in a later second would get a 409. Bounded; expired entries are dropped. */
  private readonly expiries = new Map<string, { text: string; at: number }>();

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
    this.events = new EventsApi(this, typeof opts.token === "string" && opts.token.length > 0);
  }

  /** ONEMIND_HUB + ONEMIND_TOKEN, else ONEMIND_GATEWAY_URL + ONEMIND_AGENT_TOKEN (contract §11.2).
   *  With ONEMIND_GATEWAY_CA (PEM text) set, the client verifies TLS against that CA only (Node). */
  static fromEnv(env: Record<string, string | undefined> = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {}, extra: Partial<ClientOptions> = {}) {
    const hub = env.ONEMIND_HUB || env.ONEMIND_GATEWAY_URL;
    if (!hub) throw new Error("onemind: set ONEMIND_HUB (and ONEMIND_TOKEN) or ONEMIND_GATEWAY_URL");
    const token = env.ONEMIND_HUB ? env.ONEMIND_TOKEN : env.ONEMIND_AGENT_TOKEN;
    // ONEMIND_GATEWAY_CA (PEM): trust the box CA for this client, Node only; `extra.fetch` still wins.
    const ca = env.ONEMIND_GATEWAY_CA?.trim();
    return new OneMind({ ...(ca ? { fetch: caFetch(ca) } : {}), ...extra, baseUrl: hub, token: token ?? "" });
  }

  toString(): string {
    return `OneMind(hub=${this.baseUrl}, principal=${this.principal ?? "?"})`;
  }

  /** The hub's clock as last seen in a Date header. */
  hubNow(): number {
    return Date.now() + this.offsetMs;
  }

  private expiryFor(key: string | undefined, spanMs: number): string {
    const now = this.hubNow();
    const fmt = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
    if (key === undefined) return fmt(now + spanMs);
    const hit = this.expiries.get(key);
    if (hit && hit.at > now) return hit.text;
    const text = fmt(now + spanMs);
    this.expiries.delete(key);
    this.expiries.set(key, { text, at: now + spanMs });
    for (const [k, v] of this.expiries) if (v.at <= now) this.expiries.delete(k);
    while (this.expiries.size > 1024) this.expiries.delete(this.expiries.keys().next().value as string);
    return text;
  }

  hubOffsetMs(): number {
    return this.offsetMs;
  }

  // ---- operations ------------------------------------------------------------------------------
  async healthz(): Promise<boolean> {
    return ((await this.call<{ ok: boolean }>({ method: "GET", path: "/healthz" })) ?? { ok: false }).ok;
  }

  readonly instance = {
    get: () => this.call<Instance>({ method: "GET", path: "/v1/instance" }),
    /** The box's own screen as the full-screen dashboard. Owner only; the screen switches within seconds. */
    kiosk: {
      get: () => this.call<KioskState>({ method: "GET", path: "/v1/instance/kiosk" }),
      set: (enabled: boolean) => this.call<KioskState>({ method: "PUT", path: "/v1/instance/kiosk", body: { enabled } }),
    },
  };

  /** Bring your own domain (NET-DOM-01, owner only). A domain is proved with a TXT record; approving a name records a decision only. */
  readonly domains = {
    list: () => this.call<DomainsSummary>({ method: "GET", path: "/v1/domains" }),
    add: (domain: string) => this.call<DomainView>({ method: "POST", path: "/v1/domains", body: { domain } }),
    check: (domain: string) =>
      this.call<{ domain: DomainView; proof_found: boolean }>({ method: "POST", path: `/v1/domains/${encodeURIComponent(domain)}/check` }),
    remove: (domain: string) => this.call<void>({ method: "DELETE", path: `/v1/domains/${encodeURIComponent(domain)}` }),
    /** Ask for `<app>.<domain>`. It stays "requested" until the owner approves the name, typed in full. */
    requestHost: (domain: string, appId: string) =>
      this.call<DomainHost>({ method: "POST", path: `/v1/domains/${encodeURIComponent(domain)}/hosts`, body: { app_id: appId } }),
    /** Approve one name: `confirm` must be the hostname typed in full. Records a decision only; nothing is served yet. */
    approveHost: (hostname: string, confirm: string) =>
      this.call<DomainHost>({ method: "POST", path: `/v1/domains/hosts/${encodeURIComponent(hostname)}/approve`, body: { confirm } }),
    /** Withdraw a requested or approved name. */
    removeHost: (hostname: string) => this.call<void>({ method: "DELETE", path: `/v1/domains/hosts/${encodeURIComponent(hostname)}` }),
  };

  /** status.get (FD-01): what needs attention, per source. A source that cannot be read is "unknown", never "ok". */
  readonly status = { get: () => this.call<StatusView>({ method: "GET", path: "/v1/status" }) };

  readonly nodes = {
    list: () => this.call<Node[]>({ method: "GET", path: "/v1/nodes" }),
    get: (id: string) => this.call<Node>({ method: "GET", path: `/v1/nodes/${encodeURIComponent(id)}` }),
  };

  readonly network = {
    view: () => this.call<NetworkView>({ method: "GET", path: "/v1/network" }),
    /** network.firewall (P-09 part 1): what the box's firewall lets in, and from where. Read only. */
    firewall: () => this.call<FirewallView>({ method: "GET", path: "/v1/network/firewall" }),
    /** network.firewall.allow (P-09 part 2): files a `firewall.allow` action; an owner approves it with a passkey,
     * then the rule is pending until `confirmAllow`. Safe to retry (one idempotency key). */
    allow: (input: AllowRequest) => this.call<Action>({ method: "POST", path: "/v1/network/firewall/allow", body: input, retry: true }),
    /** network.firewall.allow.confirm: keep a pending rule (owner only). A rule that reverted already is a 404. */
    confirmAllow: (id: string) => this.call<{ id: string; state: string }>({ method: "POST", path: `/v1/network/firewall/allow/${encodeURIComponent(id)}/confirm` }),
    /** network.firewall.allow.remove: take a rule away, pending or confirmed (owner only). */
    removeAllow: (id: string) => this.call<{ id: string; removed: boolean }>({ method: "DELETE", path: `/v1/network/firewall/allow/${encodeURIComponent(id)}` }),
    /** Ask for a fixed address or DHCP on a cable interface. Files an action an owner approves with a passkey; nothing changes before. */
    configure: (iface: string, body: NetworkConfigBody) =>
      this.call<Action>({ method: "PUT", path: `/v1/network/${encodeURIComponent(iface)}`, body, retry: true }),
    /** Keep the identified change after verifying the dashboard loads at the interface's new IPv4 address. */
    confirm: (iface: string, body: NetworkConfirmBody) =>
      this.call<NetworkConfirm>({ method: "POST", path: `/v1/network/${encodeURIComponent(iface)}/confirm`, body }),
  };

  // Tips are served by the hub. Do not follow a redirect out to a content host.
  readonly tips = {
    list: () => this.call<components["schemas"]["TipList"]>({
      method: "GET", path: "/v1/tips", redirect: "error",
    }),
    collections: () => this.call<components["schemas"]["TipCollections"]>({
      method: "GET", path: "/v1/tips/collections", redirect: "error",
    }),
    /** What changed in the running OneMind version, from the Tips pack that ships in the image. */
    whatsNew: () => this.call<components["schemas"]["TipWhatsNew"]>({
      method: "GET", path: "/v1/tips/whats-new", redirect: "error",
    }),
    get: (id: string) => this.call<components["schemas"]["TipView"]>({
      method: "GET", path: `/v1/tips/${encodeURIComponent(id)}`, redirect: "error",
    }),
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
        expires_at: input.expiresAt ?? this.expiryFor(input.idempotencyKey, input.expiresInMs ?? 24 * 3600_000),
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

  readonly me = {
    home: {
      /** The caller's resolved Home and its ETag. */
      get: async (): Promise<HomeWithEtag> => {
        const { body, headers } = await this.raw<HomeView>({ method: "GET", path: "/v1/me/home", retry: true });
        return { home: body, etag: headers.get("etag") ?? "" };
      },
      /** Replace the whole document; `etag` is the one read last (a stale one answers 412). */
      save: async (doc: HomeBody, etag: string): Promise<HomeWithEtag> => {
        const { body, headers } = await this.raw<HomeView>({ method: "PUT", path: "/v1/me/home", body: doc, headers: { "If-Match": etag } });
        return { home: body, etag: headers.get("etag") ?? "" };
      },
    },
  };

  readonly notifications = {
    devices: () => this.call<components['schemas']['PushRegistration'][]>({ method: 'GET', path: '/v1/push/registrations', retry: true }),
    createChannel: (body: components['schemas']['ChannelIn']) =>
      this.call<unknown>({ method: 'POST', path: '/v1/notifications/channels', body }),
    preferences: {
      /** The caller's routing document (quiet hours, routes, digest) and its ETag. */
      get: async (): Promise<NotificationPreferencesWithEtag> => {
        const { body, headers } = await this.raw<Record<string, unknown>>({ method: "GET", path: "/v1/notifications/preferences", retry: true });
        return { prefs: body, etag: headers.get("etag") ?? "" };
      },
      /** Replace the whole document; a stale `etag` answers 409 (never retried). */
      save: async (doc: Record<string, unknown>, etag: string): Promise<NotificationPreferencesWithEtag> => {
        const { body, headers } = await this.raw<Record<string, unknown>>({ method: "PUT", path: "/v1/notifications/preferences", body: doc, headers: { "If-Match": etag } });
        return { prefs: body, etag: headers.get("etag") ?? "" };
      },
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
        redirect: r.redirect,
        method: r.method,
        headers: {
          Accept: "application/json",
          [PROTOCOL_HEADER]: String(PROTOCOL_VERSION),
          ...(r.body !== undefined ? { "Content-Type": "application/json" } : {}),
          ...(r.headers ?? {}),
          ...(await this.authHeader()),
        },
        body: r.body !== undefined ? JSON.stringify(r.body) : undefined,
        signal: ctrl.signal,
        ...(r.redirect ? { redirect: r.redirect } : {}),
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
