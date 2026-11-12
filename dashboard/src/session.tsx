import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { HttpApi, type OneMindApi } from './api/client';
import { DEMO_TOKENS } from './api/fixtures';
import { MockApi } from './api/mock';
import type { Principal } from './api/types';

/**
 * Can the signed-in principal approve or deny?
 * - 'yes' / 'no' when we know the role (mock mode, or after the gateway said 403).
 * - 'unknown' against a real gateway: contract v0 has no "who am I" route, so we
 *   leave the buttons on and let the gateway enforce owner-only (it returns 403
 *   permission_denied, after which we switch to 'no'). The gateway is the
 *   security boundary; the UI only avoids offering what will be refused.
 */
export type DecideAbility = 'yes' | 'no' | 'unknown';

export interface Session {
  token: string;
  api: OneMindApi;
  principal: Principal | undefined;
  canDecide: DecideAbility;
  canRequest: DecideAbility;
  mock: boolean;
}

interface SessionCtx {
  session: Session | null;
  signIn(token: string): Promise<void>;
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
  const api = deps.makeApi ? deps.makeApi(token) : deps.mock ? new MockApi(token) : new HttpApi({ token });
  const principal = deps.knownPrincipal ? deps.knownPrincipal(token) : deps.mock ? DEMO_TOKENS[token] : undefined;
  const canDecide: DecideAbility = principal ? (principal.role === 'owner' ? 'yes' : 'no') : 'unknown';
  const canRequest: DecideAbility = principal
    ? principal.role === 'owner' || principal.kind === 'agent'
      ? 'yes'
      : 'no'
    : 'unknown';
  return { token, api, principal, canDecide, canRequest, mock: deps.mock };
}

export function SessionProvider({ deps, children }: { deps: SessionDeps; children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => {
    const t = readStored();
    return t ? build(t, deps) : null;
  });

  const signIn = useCallback(
    async (token: string) => {
      const s = build(token.trim(), deps);
      await s.api.instance(); // throws ApiError(401) on a bad token
      writeStored(s.token);
      setSession(s);
    },
    [deps],
  );

  const signOut = useCallback(() => {
    writeStored(null);
    setSession(null);
  }, []);

  const markForbidden = useCallback(() => {
    setSession((s) => (s ? { ...s, canDecide: 'no' } : s));
  }, []);

  const value = useMemo(() => ({ session, signIn, signOut, markForbidden }), [session, signIn, signOut, markForbidden]);
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
  return { ...c.session, signIn: c.signIn, signOut: c.signOut, markForbidden: c.markForbidden };
}
