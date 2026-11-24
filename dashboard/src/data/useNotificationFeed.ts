// SPDX-License-Identifier: Apache-2.0
// The bell's data: GET /v1/notifications and the open alerts, refreshed the moment the hub's event
// stream says something changed. If the stream is not there (mock gateway, an older hub, a proxy
// that buffers) the same two lists are polled every 30 s, so the bell is never frozen.
import { useEffect, useRef, useState } from 'react';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

export const POLL_FALLBACK_MS = 30_000;
/** While the stream is up it is the trigger; this slow poll covers a missed event or a proxy that buffers the stream. */
export const POLL_LIVE_MS = 60_000;
/** Events arrive in bursts (an action moves through several states): refresh once per burst. */
const BURST_MS = 800;

export function useNotificationFeed() {
  const { api, principal } = useSignedIn();
  const [live, setLive] = useState(false);
  const every = live ? POLL_LIVE_MS : POLL_FALLBACK_MS;
  // Guests cannot read alerts (403); a failed list is simply absent, never an error banner.
  const notes = usePoll(() => api.notifications({ limit: 100 }), every);
  const alerts = usePoll(() => api.alerts('open'), every);
  const reloads = useRef({ notes: notes.reload, alerts: alerts.reload });
  reloads.current = { notes: notes.reload, alerts: alerts.reload };

  useEffect(() => {
    if (!api.watchEvents) return;
    const ctrl = new AbortController();
    let timer: number | undefined;
    const burst = () => {
      if (timer !== undefined) return;
      timer = window.setTimeout(() => {
        timer = undefined;
        void reloads.current.notes();
        void reloads.current.alerts();
      }, BURST_MS);
    };
    setLive(true);
    api.watchEvents(burst, ctrl.signal).then(
      () => setLive(false),
      () => setLive(false),
    );
    return () => {
      ctrl.abort();
      window.clearTimeout(timer);
      setLive(false);
    };
  }, [api, principal?.id]);

  return { notifications: notes.data, alerts: alerts.data, live, reload: () => { void notes.reload(); void alerts.reload(); } };
}
