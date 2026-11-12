// SPDX-License-Identifier: Apache-2.0
// One poll for the whole app: instance, nodes, apps and actions every 10 s (the
// heartbeat interval, §1) while the app is in the foreground. Every screen, the
// Approvals badge and the local notifications read from this one source, so they
// never disagree. On error the last data is kept and marked with its age.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppState } from 'react-native';
import { ApiError, type Action, type CatalogApp, type Instance, type NodeRecord } from './api/types';
import { diffAlerts, snapshot, type Alert, type Snapshot } from './lib/alerts';
import { useSession, useSignedIn } from './session';

export interface HubData {
  instance?: Instance;
  nodes?: NodeRecord[];
  apps?: CatalogApp[];
  actions?: Action[];
  /** Phone time (ms) of the last fully successful refresh. */
  fetchedAt?: number;
  /** Hub clock minus phone clock (ms), from the Date header. */
  hubOffsetMs?: number;
  error?: ApiError;
  loading: boolean;
  refreshing: boolean;
  reload(): Promise<void>;
  pendingCount: number;
}

const Ctx = createContext<HubData | null>(null);

export const POLL_MS = 10_000;

export function HubDataProvider({
  children,
  onAlerts,
  intervalMs = POLL_MS,
}: {
  children: ReactNode;
  onAlerts?: (alerts: Alert[]) => void;
  intervalMs?: number;
}) {
  const { api } = useSignedIn();
  const { disconnect } = useSession();
  const [state, setState] = useState<Omit<HubData, 'reload' | 'pendingCount' | 'refreshing'>>({ loading: true });
  const [refreshing, setRefreshing] = useState(false);
  const prev = useRef<Snapshot | undefined>(undefined);
  const seq = useRef(0);
  const alertsRef = useRef(onAlerts);
  alertsRef.current = onAlerts;

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const [instance, nodes, apps, actions] = await Promise.all([api.instance(), api.nodes(), api.apps(), api.actions()]);
      if (mine !== seq.current) return; // a newer refresh started; drop this answer
      const snap = snapshot(actions, nodes);
      const alerts = diffAlerts(prev.current, snap, actions, nodes);
      prev.current = snap;
      setState({ instance, nodes, apps, actions, fetchedAt: Date.now(), hubOffsetMs: api.hubOffsetMs(), loading: false });
      if (alerts.length) alertsRef.current?.(alerts);
    } catch (e) {
      if (mine !== seq.current) return;
      const err = e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e));
      if (err.code === 'unauthenticated') {
        void disconnect();
        return;
      }
      setState((s) => ({ ...s, error: err, loading: false }));
    }
  }, [api, disconnect]);

  const reload = useCallback(async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    const start = () => {
      if (timer === undefined && intervalMs > 0) timer = setInterval(() => void load(), intervalMs);
    };
    const stop = () => {
      if (timer !== undefined) clearInterval(timer);
      timer = undefined;
    };
    void load();
    start();
    const sub = AppState.addEventListener('change', (s) => {
      if (s === 'active') {
        void load();
        start();
      } else stop();
    });
    return () => {
      stop();
      sub.remove();
      seq.current++;
    };
  }, [load, intervalMs]);

  const value = useMemo<HubData>(
    () => ({
      ...state,
      refreshing,
      reload,
      pendingCount: (state.actions ?? []).filter((a) => a.state === 'awaiting_approval').length,
    }),
    [state, refreshing, reload],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useHubData(): HubData {
  const c = useContext(Ctx);
  if (!c) throw new Error('useHubData outside HubDataProvider');
  return c;
}

/** A clock that ticks, so "last seen 12s ago" keeps counting between polls. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}
