// SPDX-License-Identifier: Apache-2.0
// One poll of the hub shared by every screen: instance, nodes, apps and actions (contract §3).
// Screens read from here instead of fetching on their own, so Home, the Market, the bell and the
// palette always agree. Requests and decisions go through `request` and `decide`, which follow
// an action by polling `GET /v1/actions/{id}` until it ends (live install progress).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError, type Action, type ActionType, type CatalogApp, type Instance, type NodeRecord, type NodeStatus } from '../api/types';
import { usePoll, useNow, type Polled } from '../lib/hooks';
import { effectiveStatus, OFFLINE_AFTER_S, STALE_AFTER_S } from '../lib/time';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn, type DecideAbility } from '../session';
import { isActive } from './adapters';

/** How long an owner has to decide on a request (§11.3 and §12.1 use 24 h). */
export const REQUEST_TTL_MS = 24 * 60 * 60 * 1000;
/** Poll interval while an action is moving, and otherwise (heartbeats arrive every 10 s, §1). */
export const FOLLOW_MS = 2000;
export const POLL_MS = 10_000;

export type HubFreshness = 'live' | 'stale' | 'offline' | 'unknown';

export interface Hub {
  /** Hub clock (ms), ticking every second. */
  now: number;
  instance: Polled<Instance>;
  nodes: Polled<NodeRecord[]>;
  apps: Polled<CatalogApp[]>;
  actions: Polled<Action[]>;
  /** The actions list with followed actions merged in (newest answer per id). */
  actionList: Action[];
  /** Node status aged on the hub clock: never shown as live after the answer gets old. */
  nodeStatus: (n: NodeRecord) => NodeStatus;
  /** How fresh the hub's answers are, from the oldest of the polls. */
  freshness: HubFreshness;
  /** Age (s) of the oldest answer, undefined before the first. */
  ageS: number | undefined;
  /** When the oldest answer was fetched, on the hub clock (ISO), for "as of". */
  asOf: string | undefined;
  appName: (id: string) => string;
  canDecide: DecideAbility;
  canRequest: DecideAbility;
  /** Ids of actions with a decision in flight. */
  busy: ReadonlySet<string>;
  request: (type: ActionType, appId: string) => Promise<Action>;
  decide: (id: string, how: 'approve' | 'deny') => Promise<Action>;
  reloadAll: () => void;
}

const Ctx = createContext<Hub | null>(null);

export function useHub(): Hub {
  const h = useContext(Ctx);
  if (!h) throw new Error('useHub outside HubProvider');
  return h;
}

function newest(a: Action, b: Action): Action {
  const ta = Date.parse(a.updated_at ?? '') || 0;
  const tb = Date.parse(b.updated_at ?? '') || 0;
  return tb > ta ? b : a;
}

export function HubProvider({ children }: { children: ReactNode }) {
  const { api, canDecide, canRequest, markForbidden } = useSignedIn();
  const browserNow = useNow(1000);
  const [followed, setFollowed] = useState<Record<string, Action>>({});
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  // One idempotency key per (type, app) until the hub gives a definite answer (§3): a retry after
  // a lost response returns the same action instead of creating a second one.
  const keys = useRef(new Map<string, { key: string; expiresAt: string }>());

  const instance = usePoll(() => api.instance(), 60_000);
  const nodes = usePoll(() => api.nodes(), POLL_MS);
  const following = Object.values(followed).some(isActive);
  const actions = usePoll(() => api.actions(), following ? FOLLOW_MS : POLL_MS);
  const apps = usePoll(() => api.apps(), following ? FOLLOW_MS : POLL_MS * 3);

  // Follow each moving action by id until it ends (the list poll may be slower or paginated later).
  useEffect(() => {
    const ids = Object.values(followed).filter(isActive).map((a) => a.id);
    if (ids.length === 0) return;
    const t = window.setInterval(() => {
      for (const id of ids)
        api.action(id).then(
          (a) => setFollowed((f) => ({ ...f, [id]: f[id] ? newest(f[id]!, a) : a })),
          () => undefined,
        );
    }, FOLLOW_MS);
    return () => window.clearInterval(t);
  }, [api, followed]);

  const actionList = useMemo(() => {
    const byId = new Map((actions.data ?? []).map((a) => [a.id, a]));
    for (const f of Object.values(followed)) byId.set(f.id, byId.has(f.id) ? newest(byId.get(f.id)!, f) : f);
    return [...byId.values()].sort((x, y) => Date.parse(y.created_at ?? '') - Date.parse(x.created_at ?? ''));
  }, [actions.data, followed]);

  const offset = api.hubOffsetMs() ?? 0;
  const now = browserNow + offset;
  const fetched = [nodes.fetchedAt, apps.fetchedAt, actions.fetchedAt];
  const oldest = fetched.some((f) => f === undefined) ? undefined : Math.min(...(fetched as number[]));
  const ageS = oldest === undefined ? undefined : Math.max(0, Math.floor((browserNow - oldest) / 1000));
  const freshness: HubFreshness = ageS === undefined ? 'unknown' : ageS >= OFFLINE_AFTER_S ? 'offline' : ageS >= STALE_AFTER_S ? 'stale' : 'live';

  const names = useMemo(() => new Map((apps.data ?? []).map((a) => [a.id, a.name || a.id])), [apps.data]);
  const appName = useCallback((id: string) => names.get(id) ?? id, [names]);
  const nodeFetched = nodes.fetchedAt;
  const nodeStatus = useCallback(
    (n: NodeRecord) => effectiveStatus(n.status, n.last_seen, browserNow, { fetchedAt: nodeFetched, hubOffsetMs: api.hubOffsetMs() }),
    [browserNow, nodeFetched, api],
  );

  const { reload: reloadActions } = actions;
  const { reload: reloadApps } = apps;
  const request = useCallback(
    async (type: ActionType, appId: string) => {
      const slot = `${type}:${appId}`;
      let k = keys.current.get(slot);
      if (!k) {
        k = { key: uuidv4(), expiresAt: new Date(Date.now() + offset + REQUEST_TTL_MS).toISOString() };
        keys.current.set(slot, k);
      }
      try {
        const a = await api.createAction({ type, params: { app_id: appId }, idempotency_key: k.key, expires_at: k.expiresAt });
        keys.current.delete(slot);
        setFollowed((f) => ({ ...f, [a.id]: a }));
        void reloadActions();
        return a;
      } catch (e) {
        // Keep the key only when the outcome is unknown (network error or 5xx).
        if (!(e instanceof ApiError) || (e.status >= 400 && e.status < 500)) keys.current.delete(slot);
        throw e;
      }
    },
    [api, offset, reloadActions],
  );

  const decide = useCallback(
    async (id: string, how: 'approve' | 'deny') => {
      setBusy((b) => new Set(b).add(id));
      try {
        const a = how === 'approve' ? await api.approve(id) : await api.deny(id);
        setFollowed((f) => ({ ...f, [a.id]: a }));
        void reloadActions();
        void reloadApps();
        return a;
      } catch (e) {
        if (e instanceof ApiError && e.code === 'permission_denied') markForbidden();
        void reloadActions();
        throw e;
      } finally {
        setBusy((b) => {
          const n = new Set(b);
          n.delete(id);
          return n;
        });
      }
    },
    [api, reloadActions, reloadApps, markForbidden],
  );

  // When a followed action ends, refresh the catalog once so "installed" shows at once.
  const ended = Object.values(followed).filter((a) => !isActive(a)).map((a) => a.id).join(',');
  useEffect(() => {
    if (ended) void reloadApps();
  }, [ended, reloadApps]);

  const reloadAll = useCallback(() => {
    void instance.reload();
    void nodes.reload();
    void apps.reload();
    void actions.reload();
  }, [instance, nodes, apps, actions]);

  const value: Hub = {
    now,
    instance,
    nodes,
    apps,
    actions,
    actionList,
    nodeStatus,
    freshness,
    ageS,
    asOf: oldest === undefined ? undefined : new Date(oldest + offset).toISOString(),
    appName,
    canDecide,
    canRequest,
    busy,
    request,
    decide,
    reloadAll,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Plain words for an ApiError, for toasts. */
export function errorText(e: unknown): { code: string; message: string } {
  if (e instanceof ApiError) {
    if (e.code === 'permission_denied') return { code: e.code, message: 'Your account is not allowed to do this. Only the owner approves; owners and agents request.' };
    if (e.code === 'stale_precondition') return { code: e.code, message: `The hub refused: ${e.message}` };
    if (e.code === 'network') return { code: e.code, message: 'The hub did not answer. Nothing was changed; try again.' };
    return { code: e.code, message: e.message };
  }
  return { code: 'unknown', message: e instanceof Error ? e.message : String(e) };
}
