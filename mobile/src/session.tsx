// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Features, HttpApi, normalizeHubUrl, OP, type OneMindApi, type TokenSource } from './api/client';
import { DEMO_TOKENS } from './api/fixtures';
import { MockApi } from './api/mock';
import type { LoginResult, Me, Principal } from './api/types';
import { clearConnection, loadConnection, saveConnection, type Connection, type LiveConnection } from './storage';

/**
 * Can this person approve, deny or request? With `GET /v1/me` (§12.6) the hub says so. On a v0 hub
 * there is no "who am I" route, so the answer is 'unknown' until the hub says 403; the buttons stay
 * on and the gateway enforces owner-only. Same rule as the dashboard.
 */
export type Ability = 'yes' | 'no' | 'unknown';

export interface Session {
  connection: Connection;
  api: OneMindApi;
  principal: Principal | undefined;
  /** §12.6 identity, when the hub serves /v1/me. */
  me: Me | undefined;
  /** Which §12 routes this hub serves (read from /openapi.json after connecting). */
  features: Features;
  canDecide: Ability;
  canRequest: Ability;
  /** Shown in the header: hub host, or "Demo". */
  label: string;
  /** False when the secure store refused the save: the session lasts until the app closes. */
  remembered: boolean;
}

export interface SessionDeps {
  makeApi?: (c: Connection, tokens: TokenSource) => OneMindApi;
  load?: () => Promise<Connection | null>;
  save?: (c: Connection) => Promise<void>;
  clear?: () => Promise<void>;
  /** Device-bound renewal (lib/device: DPoP proof with this phone's key). Undefined when not registered. */
  renewWithDevice?: (api: OneMindApi, features: Features, hubUrl: string) => Promise<LoginResult | undefined>;
}

interface SessionCtx {
  ready: boolean;
  session: Session | null;
  /** Set when a sign-in expired and could not be renewed: the Connect screen offers this hub again. */
  expiredHub: string | undefined;
  connect(c: Connection): Promise<void>;
  /** Forget this hub on this phone (secure store entries, best-effort sign-out on the hub). */
  disconnect(): Promise<void>;
  /** The hub refused the session: back to sign-in with the hub address kept. */
  expire(): Promise<void>;
  markForbidden(): void;
  /** Re-read /v1/me (after adding a passkey, for example). */
  refreshIdentity(): Promise<void>;
}

const Ctx = createContext<SessionCtx | null>(null);

/** Things to forget with the hub (device link, push registration); modules add theirs. */
const forgetHooks = new Set<(api: OneMindApi, hubUrl: string) => Promise<void>>();
export function onForgetHub(fn: (api: OneMindApi, hubUrl: string) => Promise<void>): () => void {
  forgetHooks.add(fn);
  return () => forgetHooks.delete(fn);
}

function defaultApi(c: Connection, tokens: TokenSource): OneMindApi {
  return c.mode === 'mock' ? new MockApi(c.token) : new HttpApi({ tokens, baseUrl: c.hubUrl });
}

/** Abilities from §12.6 `/v1/me`. Unknown roles count as the least privileged (§12.6). */
export function abilitiesFromMe(me: Me): { canDecide: Ability; canRequest: Ability } {
  const caps = new Set(me.capabilities ?? []);
  const owner = me.principal.kind === 'person' && me.principal.role === 'owner';
  const canDecide: Ability = caps.has('can_approve') ? 'yes' : owner && caps.size === 0 ? 'unknown' : 'no';
  const requestScope = (me.token?.scopes ?? []).some((s) => s === 'actions:request' || s.startsWith('actions:request:'));
  const canRequest: Ability = caps.has('can_request') || requestScope || owner ? 'yes' : 'no';
  return { canDecide, canRequest };
}

export function buildSession(c: Connection, makeApi: (c: Connection, tokens: TokenSource) => OneMindApi = defaultApi, tokens?: TokenSource): Session {
  const principal = c.mode === 'mock' ? DEMO_TOKENS[c.token] : undefined;
  const canDecide: Ability = principal ? (principal.role === 'owner' ? 'yes' : 'no') : 'unknown';
  const canRequest: Ability = principal ? (principal.role === 'owner' || principal.kind === 'agent' ? 'yes' : 'no') : 'unknown';
  let label = 'Demo';
  if (c.mode === 'live') {
    try {
      label = new URL(c.hubUrl).host;
    } catch {
      label = c.hubUrl;
    }
  }
  const t = tokens ?? { current: () => c.token };
  return { connection: c, api: makeApi(c, t), principal, me: undefined, features: Features.none(), canDecide, canRequest, label, remembered: true };
}

/** Read features and identity from the hub. Never throws: a v0 hub simply has neither. */
async function enrich(s: Session): Promise<Session> {
  const features = await s.api.features().catch(() => Features.none());
  let me: Me | undefined;
  if (features.has(OP.me)) me = await s.api.me().catch(() => undefined);
  if (!me) return { ...s, features };
  const { kind, role, id } = me.principal;
  return { ...s, features, me, principal: { id, kind, role }, ...abilitiesFromMe(me) };
}

export function SessionProvider({ deps = {}, children }: { deps?: SessionDeps; children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [expiredHub, setExpiredHub] = useState<string>();
  const { makeApi = defaultApi, load = loadConnection, save = saveConnection, clear = clearConnection, renewWithDevice } = deps;
  const conn = useRef<Connection | null>(null);
  const live = useRef<Session | null>(null);
  live.current = session;

  /** Bearer for every request; renews a passkey session once when the hub says it expired. */
  const tokens = useMemo<TokenSource>(
    () => ({
      current: () => conn.current?.token,
      refresh: async () => {
        const c = conn.current;
        const s = live.current;
        if (!c || c.mode !== 'live' || c.auth !== 'passkey' || !s) return undefined;
        // Right after start the session may not know the hub's routes yet (enrich still running): ask now.
        const features = s.features.source === 'unknown' ? await s.api.features().catch(() => s.features) : s.features;
        let r: LoginResult | undefined;
        try {
          r = await renewWithDevice?.(s.api, features, c.hubUrl);
        } catch {
          r = undefined;
        }
        if (!r && c.refreshToken && features.has(OP.authRefresh)) r = await s.api.refreshSession(c.refreshToken).catch(() => undefined);
        if (!r) return undefined;
        const next: LiveConnection = { ...c, token: r.access_token, expiresAt: r.expires_at, refreshToken: r.refresh_token ?? c.refreshToken };
        conn.current = next;
        await save(next).catch(() => undefined);
        setSession((x) => (x ? { ...x, connection: next } : x));
        return next.token;
      },
    }),
    [renewWithDevice, save],
  );

  const adopt = useCallback(
    (c: Connection) => {
      conn.current = c;
      return buildSession(c, makeApi, tokens);
    },
    [makeApi, tokens],
  );

  useEffect(() => {
    let alive = true;
    void load().then((c) => {
      if (!alive) return;
      if (c) {
        const s = adopt(c);
        setSession(s);
        // Show the app at once; features and identity follow (an unreachable hub must not block the start).
        void enrich(s).then((e) => alive && setSession((cur) => (cur?.api === s.api ? { ...e, connection: cur.connection } : cur)));
      }
      setReady(true);
    });
    return () => {
      alive = false;
    };
    // Load once at start; deps are stable for the app's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = useCallback(
    async (raw: Connection) => {
      const c: Connection = raw.mode === 'live' ? { ...raw, hubUrl: normalizeHubUrl(raw.hubUrl), token: raw.token.trim() } : raw;
      const prev = conn.current;
      const s = adopt(c);
      try {
        await s.api.instance(); // a wrong token throws ApiError 401 before anything is saved
      } catch (e) {
        conn.current = prev;
        throw e;
      }
      let remembered = true;
      try {
        await save(c);
      } catch {
        // Secure store unavailable (e.g. an unsigned build without keychain entitlement).
        // Never fall back to plain storage; keep the session in memory only.
        remembered = false;
      }
      const e = await enrich(s);
      setExpiredHub(undefined);
      setSession({ ...e, remembered });
    },
    [adopt, save],
  );

  const disconnect = useCallback(async () => {
    const s = live.current;
    if (s && s.connection.mode === 'live') {
      for (const fn of forgetHooks) await fn(s.api, s.connection.hubUrl).catch(() => undefined);
      if (s.connection.auth === 'passkey') await s.api.logout().catch(() => undefined);
    }
    await clear();
    conn.current = null;
    setExpiredHub(undefined);
    setSession(null);
  }, [clear]);

  const expire = useCallback(async () => {
    const c = conn.current;
    await clear();
    conn.current = null;
    setExpiredHub(c?.mode === 'live' ? c.hubUrl : undefined);
    setSession(null);
  }, [clear]);

  const markForbidden = useCallback(() => setSession((s) => (s ? { ...s, canDecide: 'no' } : s)), []);

  const refreshIdentity = useCallback(async () => {
    const s = live.current;
    if (!s) return;
    const e = await enrich(s);
    setSession((cur) => (cur?.api === s.api ? { ...e, connection: cur.connection, remembered: cur.remembered } : cur));
  }, []);

  const value = useMemo(
    () => ({ ready, session, expiredHub, connect, disconnect, expire, markForbidden, refreshIdentity }),
    [ready, session, expiredHub, connect, disconnect, expire, markForbidden, refreshIdentity],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useSession outside SessionProvider');
  return c;
}

export function useSignedIn(): Session & Pick<SessionCtx, 'disconnect' | 'markForbidden' | 'refreshIdentity'> {
  const c = useSession();
  if (!c.session) throw new Error('not signed in');
  return { ...c.session, disconnect: c.disconnect, markForbidden: c.markForbidden, refreshIdentity: c.refreshIdentity };
}
