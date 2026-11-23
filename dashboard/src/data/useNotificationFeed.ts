// SPDX-License-Identifier: Apache-2.0
// The bell's data: GET /v1/notifications, its unread summary and the open alerts, refreshed the
// moment the hub's event stream says one of them changed. The stream is typed (#682): a
// notification.* event (created, read on any of this person's devices, read-all) reads the
// summary again, and a summary that moved pulls the inbox; alert.* refreshes the alerts. If the stream is not there (mock
// gateway, an older hub, a proxy that buffers) the lists are polled every 30 s, so the bell is
// never frozen, and a changed summary pulls the full list.
import { useEffect, useRef, useState } from 'react';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

export const POLL_FALLBACK_MS = 30_000;
/** While the stream is up it is the trigger; this slow poll covers a missed event or a proxy that buffers the stream. */
export const POLL_LIVE_MS = 60_000;
/** A read on another device must clear this bell within 2 s: refresh the inbox almost at once. */
export const INBOX_BURST_MS = 150;
/** Alert events arrive in bursts (an action moves through several states): refresh once per burst. */
const ALERT_BURST_MS = 800;

/** What one stream event makes stale; null for an event the bell does not show. */
export function staleBy(type: string): { inbox: boolean; alerts: boolean } | null {
  if (type === 'stream.reset') return { inbox: true, alerts: true };
  if (type.startsWith('notification.')) return { inbox: true, alerts: false };
  if (type.startsWith('alert.')) return { inbox: false, alerts: true };
  return null;
}

/** The parts of the summary that move whenever the inbox changes. */
export function summaryKey(s: { unread: number; latest_created_at?: string | null; last_read_at?: string | null } | undefined): string {
  return s ? `${s.unread}|${s.latest_created_at ?? ''}|${s.last_read_at ?? ''}` : '';
}

export function useNotificationFeed() {
  const { api, principal } = useSignedIn();
  const [live, setLive] = useState(false);
  const every = live ? POLL_LIVE_MS : POLL_FALLBACK_MS;
  // Guests cannot read alerts (403); a failed list is simply absent, never an error banner.
  const notes = usePoll(() => api.notifications({ limit: 100 }), every);
  const summary = usePoll(() => (api.notificationSummary ? api.notificationSummary() : Promise.resolve(undefined)), every);
  const alerts = usePoll(() => api.alerts('open'), every);
  const reloads = useRef({ notes: notes.reload, summary: summary.reload, alerts: alerts.reload });
  reloads.current = { notes: notes.reload, summary: summary.reload, alerts: alerts.reload };
  const hasSummary = useRef(false);
  hasSummary.current = summary.data !== undefined;

  // A summary that moved (polled, or read again after an event) means the list is stale too.
  const key = summaryKey(summary.data);
  const seen = useRef(key);
  useEffect(() => {
    if (seen.current === key) return;
    const first = seen.current === '';
    seen.current = key;
    if (!first) void reloads.current.notes();
  }, [key]);

  useEffect(() => {
    if (!api.watchEvents) return;
    const ctrl = new AbortController();
    const timers: { inbox?: number; alerts?: number } = {};
    const later = (which: 'inbox' | 'alerts', ms: number, run: () => void) => {
      if (timers[which] !== undefined) return;
      timers[which] = window.setTimeout(() => {
        timers[which] = undefined;
        run();
      }, ms);
    };
    const onEvent = (type: string) => {
      const stale = staleBy(type);
      // The cheap summary call first: when it moved, the effect above pulls the list. A hub
      // without the summary route gets the list straight away.
      if (stale?.inbox) later('inbox', INBOX_BURST_MS, () => void (hasSummary.current ? reloads.current.summary() : reloads.current.notes()));
      if (stale?.alerts) later('alerts', ALERT_BURST_MS, () => void reloads.current.alerts());
    };
    setLive(true);
    api.watchEvents(onEvent, ctrl.signal).then(
      () => setLive(false),
      () => setLive(false),
    );
    return () => {
      ctrl.abort();
      window.clearTimeout(timers.inbox);
      window.clearTimeout(timers.alerts);
      setLive(false);
    };
  }, [api, principal?.id]);

  return {
    notifications: notes.data,
    alerts: alerts.data,
    /** The hub's own unread count for this person; undefined on a hub without the summary. */
    unread: summary.data?.unread,
    live,
    reload: () => { void notes.reload(); void summary.reload(); void alerts.reload(); },
  };
}
