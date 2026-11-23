// SPDX-License-Identifier: Apache-2.0
// FD-05 (#502): the Control Hub as the live board. One subscription to GET /v1/events (through
// @onemind/sdk, which shares one feed across tabs) refreshes only the panels an event touches.
// Every panel also polls every 30 s, so a hub without the stream, a proxy that buffers it or a
// missed event never leaves the board frozen. A panel whose last refresh failed, or whose answer is
// older than three polls, says so instead of passing old data off as live.
import { useEffect, useMemo, useRef, useState } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { formatAgo, type BackupStatus, type StorageStatus } from '@onemind/ui';
import { ApiError } from '../api/types';
import type { AlertInfo, MonitoringSummary } from '../api/wiring';
import { toBackupStatus } from '../data/homeBackups';
import { toStorageStatus } from '../data/homeStorage';
import { useHub } from '../data/hub';
import { usePoll, type Polled } from '../lib/hooks';
import type { View } from '../shell/roles';
import { useSignedIn } from '../session';

/** The fallback poll for every panel (the hub's own lists poll faster, see data/hub.tsx). */
export const BOARD_POLL_MS = 30_000;
/** Three missed polls: the answer on screen is no longer "now". */
export const STALE_AFTER_S = 90;
/** Events come in bursts (an action moves through several states): refresh once per burst. */
export const BURST_MS = 500;

/** What a panel reads; an event names the reads it makes out of date. */
export type Feed = 'alerts' | 'summary' | 'nodes' | 'apps' | 'actions' | 'storage' | 'backups';

/** Panels on the board, in order. `kubernetes` is cluster detail: only the Pro view shows it. */
export type PanelId = 'summary' | 'alerts' | 'apps' | 'nodes' | 'storage' | 'backups' | 'slots' | 'kubernetes';
const PANELS: readonly PanelId[] = ['summary', 'alerts', 'apps', 'nodes', 'storage', 'backups', 'slots', 'kubernetes'];
const PRO_ONLY: ReadonlySet<PanelId> = new Set(['kubernetes']);

/** Simple mode hides Kubernetes; anything but a known Pro role gets the simple set (fail closed). */
export function boardPanels(view: View): PanelId[] {
  return PANELS.filter((p) => view === 'pro' || !PRO_ONLY.has(p));
}

/**
 * Which reads an event makes out of date (the §12.8 types in core eventstream.py). Backup runs,
 * storage changes and app changes are all actions, so an action event refreshes those too.
 */
export function feedsFor(type: string): Feed[] {
  if (type.startsWith('alert.')) return ['alerts', 'summary'];
  if (type === 'node.status') return ['nodes', 'summary'];
  if (type.startsWith('app.')) return ['apps', 'summary'];
  if (type.startsWith('action.')) return ['actions', 'apps', 'storage', 'backups'];
  if (type.startsWith('audit.')) return ['storage', 'backups'];
  return [];
}

/** Why a panel's data is not current, in words; undefined while it is current or not loaded yet. */
export function staleNote(p: Pick<Polled<unknown>, 'data' | 'error' | 'fetchedAt'>, nowMs: number): string | undefined {
  if (p.data === undefined || p.fetchedAt === undefined) return undefined;
  const ageS = Math.max(0, Math.round((nowMs - p.fetchedAt) / 1000));
  if (p.error) return `Could not refresh: showing what the hub said ${formatAgo(ageS)}.`;
  if (ageS >= STALE_AFTER_S) return `Not refreshed since ${formatAgo(ageS)}: this may be out of date.`;
  return undefined;
}

export interface Board {
  /** The event stream is open: panels change as the hub reports, not only every 30 s. */
  live: boolean;
  alerts: Polled<AlertInfo[]>;
  summary: Polled<MonitoringSummary>;
  /** null: this hub does not report it (the demo gateway). */
  storage: Polled<StorageStatus | null>;
  backups: Polled<BackupStatus | null>;
}

function toApiError(e: unknown): unknown {
  if (!(e instanceof OneMindError)) return e;
  return new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
}

/** The board's reads and the one event subscription that keeps them current. */
export function useBoard(): Board {
  const { api, token, mock } = useSignedIn();
  const hub = useHub();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const read = async (path: string): Promise<unknown> => {
    try {
      return await sdk.call<unknown>({ method: 'GET', path });
    } catch (e) {
      throw toApiError(e);
    }
  };
  const alerts = usePoll(() => api.alerts('open'), BOARD_POLL_MS);
  const summary = usePoll(() => api.monitoring(), BOARD_POLL_MS);
  // The demo gateway has no storage or backup service: say "not reported", never invent one.
  const storage = usePoll(async () => (mock ? null : toStorageStatus(await read('/v1/storage'), new Date().toISOString())), BOARD_POLL_MS);
  const backups = usePoll(async () => (mock ? null : toBackupStatus(await read('/v1/backups/status'), new Date().toISOString())), BOARD_POLL_MS);

  const reloads = useRef<Record<Feed, () => Promise<void>>>(null!);
  reloads.current = {
    alerts: alerts.reload,
    summary: summary.reload,
    storage: storage.reload,
    backups: backups.reload,
    nodes: hub.nodes.reload,
    apps: hub.apps.reload,
    actions: hub.actions.reload,
  };

  const [live, setLive] = useState(false);
  useEffect(() => {
    if (!api.watchEvents) return;
    const ctrl = new AbortController();
    const due = new Set<Feed>();
    let timer: number | undefined;
    const onEvent = (type: string) => {
      for (const f of feedsFor(type)) due.add(f);
      if (due.size === 0 || timer !== undefined) return;
      timer = window.setTimeout(() => {
        timer = undefined;
        const now = [...due];
        due.clear();
        for (const f of now) void reloads.current[f]();
      }, BURST_MS);
    };
    setLive(true);
    // Resolves when aborted; rejects when the hub has no stream (4xx). Either way the polls carry on.
    api.watchEvents(onEvent, ctrl.signal).then(
      () => setLive(false),
      () => setLive(false),
    );
    return () => {
      ctrl.abort();
      window.clearTimeout(timer);
      setLive(false);
    };
  }, [api]);

  return { live, alerts, summary, storage, backups };
}
