// SPDX-License-Identifier: Apache-2.0
// One source of hub data for the whole app: instance, nodes, apps and actions, plus the §12.14
// inbox and open alerts when the hub has them. Every screen, the badges and the local notifications
// read from here, so they never disagree. On error the last data is kept and marked with its age.
//
// Freshness: with the §12.8 event stream open, an event triggers a refresh within a moment and the
// poll drops to a 60 s safety net. Without it (v0 hub, demo, stream down) the app polls every 10 s
// (the heartbeat interval, §1) while it is in the foreground.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppState } from 'react-native';
import { OP } from './api/client';
import { ApiError, type Action, type AlertRecord, type CatalogApp, type InboxItem, type Instance, type NodeRecord } from './api/types';
import { diffAlerts, inboxAlerts, snapshot, type Alert, type Snapshot } from './lib/alerts';
import { EventStream, staleBy, type StreamState } from './lib/events';
import { useSession, useSignedIn } from './session';

export interface HubData {
  instance?: Instance;
  nodes?: NodeRecord[];
  apps?: CatalogApp[];
  actions?: Action[];
  /** §12.14 own inbox; undefined when the hub has none (v0) or the person has none (agents). */
  inbox?: InboxItem[];
  /** §12.14 open alerts visible to this person. */
  alerts?: AlertRecord[];
  /** Phone time (ms) of the last fully successful refresh. */
  fetchedAt?: number;
  /** Hub clock minus phone clock (ms), from the Date header. */
  hubOffsetMs?: number;
  error?: ApiError;
  loading: boolean;
  refreshing: boolean;
  reload(): Promise<void>;
  pendingCount: number;
  unreadCount: number;
  /** 'open' when the event stream is live; 'off' when this hub has no stream (polling only). */
  live: StreamState | 'off';
}

const Ctx = createContext<HubData | null>(null);

export const POLL_MS = 10_000;
/** While the event stream is open, poll only this often (the stream is the main signal). */
export const STREAM_POLL_MS = 60_000;
const EVENT_DEBOUNCE_MS = 300;

type State = Omit<HubData, 'reload' | 'pendingCount' | 'unreadCount' | 'refreshing' | 'live'>;

export function HubDataProvider({
  children,
  onAlerts,
  intervalMs = POLL_MS,
}: {
  children: ReactNode;
  onAlerts?: (alerts: Alert[]) => void;
  intervalMs?: number;
}) {
  const { api, features, principal, connection, refreshIdentity } = useSignedIn();
  const { disconnect, expire } = useSession();
  const [state, setState] = useState<State>({ loading: true });
  const [refreshing, setRefreshing] = useState(false);
  const [live, setLive] = useState<StreamState | 'off'>('off');
  const prev = useRef<Snapshot | undefined>(undefined);
  const seenInbox = useRef<Set<string> | undefined>(undefined);
  const seq = useRef(0);
  const lastLoad = useRef(0);
  const streamOpen = useRef(false);
  const lastIdentityTry = useRef(0);
  const alertsRef = useRef(onAlerts);
  alertsRef.current = onAlerts;

  const hasInbox = features.has(OP.notifications) && principal?.kind !== 'agent';
  const hasAlerts = features.has(OP.alerts);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    lastLoad.current = Date.now();
    try {
      const [instance, nodes, apps, actions] = await Promise.all([api.instance(), api.nodes(), api.apps(), api.actions()]);
      // Optional §12 parts: a failure here keeps the old values instead of failing the whole refresh.
      const [inboxR, alertsR] = await Promise.allSettled([
        hasInbox ? api.notifications({ limit: 100 }) : Promise.resolve(undefined),
        hasAlerts ? api.alerts('open') : Promise.resolve(undefined),
      ]);
      if (mine !== seq.current) return; // a newer refresh started; drop this answer
      const inbox = inboxR.status === 'fulfilled' ? inboxR.value : undefined;
      const alerts = alertsR.status === 'fulfilled' ? alertsR.value : undefined;
      // The hub's inbox is the source of truth when it has one; otherwise the phone diffs polls (v0).
      let raised: Alert[];
      if (hasInbox && inbox) {
        raised = inboxAlerts(seenInbox.current, inbox);
        seenInbox.current = new Set(inbox.map((n) => n.id));
      } else {
        const snap = snapshot(actions, nodes);
        raised = diffAlerts(prev.current, snap, actions, nodes);
        prev.current = snap;
      }
      setState((s) => ({
        instance,
        nodes,
        apps,
        actions,
        inbox: inbox ?? (hasInbox ? s.inbox : undefined),
        alerts: alerts ?? (hasAlerts ? s.alerts : undefined),
        fetchedAt: Date.now(),
        hubOffsetMs: api.hubOffsetMs(),
        loading: false,
      }));
      if (raised.length) alertsRef.current?.(raised);
      // Started while the hub was unreachable? Its routes were unknown then; read them now (at most once a minute).
      if (features.source === 'unknown' && connection.mode === 'live' && Date.now() - lastIdentityTry.current > 60_000) {
        lastIdentityTry.current = Date.now();
        void refreshIdentity();
      }
    } catch (e) {
      if (mine !== seq.current) return;
      const err = e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e));
      if (err.code === 'unauthenticated') {
        // A live hub refused the token and it could not be renewed: sign in again, hub address kept.
        void (connection.mode === 'live' ? expire() : disconnect());
        return;
      }
      setState((s) => ({ ...s, error: err, loading: false }));
    }
  }, [api, hasInbox, hasAlerts, features.source, connection.mode, disconnect, expire, refreshIdentity]);

  const reload = useCallback(async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  // Poll (fast without a stream, slow with one) while the app is in the foreground.
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    const tick = () => {
      if (streamOpen.current && Date.now() - lastLoad.current < STREAM_POLL_MS) return;
      void load();
    };
    const start = () => {
      if (timer === undefined && intervalMs > 0) timer = setInterval(tick, intervalMs);
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

  // The §12.8 event stream, when the hub has one. Stopped in the background (the OS would cut it anyway).
  useEffect(() => {
    const ep = features.has(OP.events) ? api.eventsEndpoint() : undefined;
    if (!ep) {
      setLive('off');
      return;
    }
    let debounce: ReturnType<typeof setTimeout> | undefined;
    const stream = new EventStream({
      url: ep.url,
      bearer: ep.bearer,
      refresh: ep.refresh,
      onEvent: (e) => {
        if (!staleBy(e).length) return;
        if (debounce !== undefined) clearTimeout(debounce);
        debounce = setTimeout(() => void load(), EVENT_DEBOUNCE_MS);
      },
      onState: (st) => {
        streamOpen.current = st === 'open';
        setLive(st);
        if (st === 'unauthenticated') void expire();
      },
    });
    if (AppState.currentState !== 'background') stream.start();
    const sub = AppState.addEventListener('change', (s) => (s === 'active' ? stream.start() : stream.stop()));
    return () => {
      sub.remove();
      stream.stop();
      streamOpen.current = false;
      if (debounce !== undefined) clearTimeout(debounce);
    };
  }, [api, features, load, expire]);

  const value = useMemo<HubData>(
    () => ({
      ...state,
      refreshing,
      reload,
      live,
      pendingCount: (state.actions ?? []).filter((a) => a.state === 'awaiting_approval').length,
      unreadCount: (state.inbox ?? []).filter((n) => !n.read_at).length,
    }),
    [state, refreshing, reload, live],
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
