// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { HttpApi, normalizeHubUrl, type OneMindApi } from './api/client';
import { DEMO_TOKENS } from './api/fixtures';
import { MockApi } from './api/mock';
import type { Principal } from './api/types';
import { clearConnection, loadConnection, saveConnection, type Connection } from './storage';

/**
 * Can this token approve, deny or request? Contract v0 has no "who am I" route,
 * so against a real hub the answer is 'unknown' until the hub says 403; the
 * buttons stay on and the gateway enforces owner-only. Same rule as the dashboard.
 */
export type Ability = 'yes' | 'no' | 'unknown';

export interface Session {
  connection: Connection;
  api: OneMindApi;
  principal: Principal | undefined;
  canDecide: Ability;
  canRequest: Ability;
  /** Shown in the header: hub host, or "Demo". */
  label: string;
  /** False when the secure store refused the save: the session lasts until the app closes. */
  remembered: boolean;
}

export interface SessionDeps {
  makeApi?: (c: Connection) => OneMindApi;
  load?: () => Promise<Connection | null>;
  save?: (c: Connection) => Promise<void>;
  clear?: () => Promise<void>;
}

interface SessionCtx {
  ready: boolean;
  session: Session | null;
  connect(c: Connection): Promise<void>;
  disconnect(): Promise<void>;
  markForbidden(): void;
}

const Ctx = createContext<SessionCtx | null>(null);

function defaultApi(c: Connection): OneMindApi {
  return c.mode === 'mock' ? new MockApi(c.token) : new HttpApi({ token: c.token, baseUrl: c.hubUrl });
}

export function buildSession(c: Connection, makeApi: (c: Connection) => OneMindApi = defaultApi): Session {
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
  return { connection: c, api: makeApi(c), principal, canDecide, canRequest, label, remembered: true };
}

export function SessionProvider({ deps = {}, children }: { deps?: SessionDeps; children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const { makeApi = defaultApi, load = loadConnection, save = saveConnection, clear = clearConnection } = deps;

  useEffect(() => {
    let alive = true;
    void load().then((c) => {
      if (!alive) return;
      if (c) setSession(buildSession(c, makeApi));
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
      const c: Connection =
        raw.mode === 'live' ? { mode: 'live', hubUrl: normalizeHubUrl(raw.hubUrl), token: raw.token.trim() } : raw;
      const s = buildSession(c, makeApi);
      await s.api.instance(); // a wrong token throws ApiError 401 before anything is saved
      let remembered = true;
      try {
        await save(c);
      } catch {
        // Secure store unavailable (e.g. an unsigned build without keychain entitlement).
        // Never fall back to plain storage; keep the session in memory only.
        remembered = false;
      }
      setSession({ ...s, remembered });
    },
    [makeApi, save],
  );

  const disconnect = useCallback(async () => {
    await clear();
    setSession(null);
  }, [clear]);

  const markForbidden = useCallback(() => setSession((s) => (s ? { ...s, canDecide: 'no' } : s)), []);

  const value = useMemo(
    () => ({ ready, session, connect, disconnect, markForbidden }),
    [ready, session, connect, disconnect, markForbidden],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useSession outside SessionProvider');
  return c;
}

export function useSignedIn(): Session & Pick<SessionCtx, 'disconnect' | 'markForbidden'> {
  const c = useSession();
  if (!c.session) throw new Error('not signed in');
  return { ...c.session, disconnect: c.disconnect, markForbidden: c.markForbidden };
}
