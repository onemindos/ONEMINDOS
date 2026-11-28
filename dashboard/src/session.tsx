// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useEffect, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { HttpApi, type OneMindApi } from './api/client';
import { DEMO_TOKENS } from './api/fixtures';
import { MockApi } from './api/mock';
import type { Principal } from './api/types';
import { personKey } from './data/prefs';
import type { PrincipalInfo } from './api/wiring';
import { readLock, saveLock, type LockSummary } from './shell/lock/state';

/**
 * Can the signed-in principal approve or deny?
 * - 'yes' / 'no' when we know the role (mock mode, or after the gateway said 403).
 * - 'unknown' against a real gateway: contract v0 has no "who am I" route, so we
 *   leave the buttons on and let the gateway enforce owner-only (it returns 403
 *   permission_denied, after which we switch to 'no'). The gateway is the
 *   security boundary; the UI only avoids offering what will be refused.
 */
export type DecideAbility = 'yes' | 'no' | 'unknown';

/** The abilities GET /v1/me reports: the gateway computes them from the token's scopes. */
export function abilitiesFromMe(me: { scopes: string[]; capabilities: string[] }): { canDecide: DecideAbility; canRequest: DecideAbility } {
  const all = me.scopes.includes('*');
  const has = (scope: string) => all || me.scopes.some((x) => x === scope || x.startsWith(`${scope}:`));
  return {
    canDecide: me.capabilities.includes('can_approve') || has('actions:approve') ? 'yes' : 'no',
    canRequest: me.capabilities.includes('can_request') || has('actions:request') ? 'yes' : 'no',
  };
}

export interface Session {
  token: string;
  api: OneMindApi;
  principal: Principal | undefined;
  /** Whose preferences this browser shows: the principal id, or a token fingerprint (prefs.ts). */
  person: string;
  account?: PrincipalInfo;
  setupPending?: boolean;
  canDecide: DecideAbility;
  canRequest: DecideAbility;
  /** True once GET /v1/me has set the two abilities from the token's scopes (or the role was known). */
  scoped: boolean;
  mock: boolean;
}

interface SessionCtx {
  session: Session | null;
  locked: LockSummary | null;
  lock(summary: LockSummary): void;
  signIn(token: string): Promise<void>;
  /** A client with no credentials, for the routes that sign a person in (login, setup, enrol). */
  anon: OneMindApi;
  signOut(): void;
  markForbidden(): void;
}

const Ctx = createContext<SessionCtx | null>(null);

export interface SessionDeps {
  mock: boolean;
  makeApi?: (token: string) => OneMindApi;
  knownPrincipal?: (token: string) => Principal | undefined;
}

const STORAGE_KEY = 'onemind.token';

function readStored(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}
function writeStored(token: string | null) {
  try {
    if (token) window.sessionStorage.setItem(STORAGE_KEY, token);
    else window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage blocked: the session just won't survive a reload */
  }
}

function build(token: string, deps: SessionDeps): Session {
  const api: OneMindApi = deps.makeApi ? deps.makeApi(token) : deps.mock ? new MockApi(token) : new HttpApi({ token });
  const principal = deps.knownPrincipal ? deps.knownPrincipal(token) : deps.mock ? DEMO_TOKENS[token] : undefined;
  const canDecide: DecideAbility = principal ? (principal.role === 'owner' ? 'yes' : 'no') : 'unknown';
  const canRequest: DecideAbility = principal
    ? principal.role === 'owner' || principal.kind === 'agent'
      ? 'yes'
      : 'no'
    : 'unknown';
  return { token, api, principal, person: personKey(principal?.id, token), canDecide, canRequest,
    scoped: !!principal, setupPending: api.setupStatus ? undefined : false, mock: deps.mock };
}

export function SessionProvider({ deps, children }: { deps: SessionDeps; children: ReactNode }) {
  const [locked, setLocked] = useState(readLock);
  const [session, setSession] = useState<Session | null>(() => {
    const t = locked ? null : readStored();
    return t ? build(t, deps) : null;
  });

  const sessionRef = useRef(session);
  const authEpoch = useRef(0);
  sessionRef.current = session;

  // Reuse the same lookup for role abilities and the first-run recovery-kit gate.
  const needsMe = !!session && (!session.scoped || session.setupPending === undefined);
  const meToken = session?.token;
  useEffect(() => {
    if (!needsMe) return;
    let live = true;
    const ask = (attempt: number) => {
      sessionRef.current?.api.me().then(
        (me) => {
          if (!live) return;
          const a = abilitiesFromMe(me);
          setSession((s) => (s && s.token === meToken ? { ...s, canDecide: s.canDecide === 'no' ? 'no' : a.canDecide,
            canRequest: a.canRequest, account: me.principal, scoped: true, setupPending: !!me.setup_pending } : s));
        },
        () => {
          if (!live) return;
          if (!attempt) setSession((s) => s && s.token === meToken ? { ...s, setupPending: false } : s);
          if (attempt < 3) timer = window.setTimeout(() => ask(attempt + 1), 1000 * 2 ** attempt);
        },
      );
    };
    let timer = 0;
    ask(0);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [needsMe, meToken]);

  const signIn = useCallback(
    async (token: string) => {
      const epoch = authEpoch.current;
      const s = build(token.trim(), deps);
      await s.api.instance(); // throws ApiError(401) on a bad token
      if (epoch !== authEpoch.current) return;
      saveLock(null);
      writeStored(s.token);
      sessionRef.current = s;
      setLocked(null);
      setSession(s);
    },
    [deps],
  );

  const endSession = useCallback((summary: LockSummary | null) => {
    ++authEpoch.current;
    // An authenticated logout is best effort. Forget the credential immediately.
    const current = sessionRef.current;
    sessionRef.current = null;
    writeStored(null);
    saveLock(summary);
    setLocked(summary);
    setSession(null);
    void current?.api.logout().catch(() => undefined);
  }, []);

  const signOut = useCallback(() => endSession(null), [endSession]);
  const lock = useCallback((summary: LockSummary) => endSession(summary), [endSession]);

  const markForbidden = useCallback(() => {
    setSession((s) => (s ? { ...s, canDecide: 'no' } : s));
  }, []);

  const anon = useMemo(() => (deps.makeApi ? deps.makeApi('') : deps.mock ? new MockApi('') : new HttpApi({ token: '' })), [deps]);
  const value = useMemo(() => ({ session, locked, lock, signIn, anon, signOut, markForbidden }), [session, locked, lock, signIn, anon, signOut, markForbidden]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useSession outside SessionProvider');
  return c;
}

/** For screens rendered behind the sign-in gate. */
export function useSignedIn(): Session & Omit<SessionCtx, 'session'> {
  const c = useSession();
  if (!c.session) throw new Error('not signed in');
  return { ...c.session, locked: c.locked, lock: c.lock, signIn: c.signIn, anon: c.anon, signOut: c.signOut, markForbidden: c.markForbidden };
}
