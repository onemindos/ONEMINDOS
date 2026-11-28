// SPDX-License-Identifier: Apache-2.0
// What the app does when a ping from the box arrives while its JavaScript runs (mobile/docs/push.md §5):
// refresh from the box, and when the app is not on screen, show the text it fetched over HTTPS.
import { Notifications } from './device/notifications';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { unifiedPush, type UnifiedPushNative } from '../modules/onemind-unifiedpush';
import type { OneMindApi } from './api/client';
import { loadPushRecord, parsePing, rotateEndpoint } from './lib/push';
import { showAlert } from './notify';
import { loadSecret, saveSecret } from './storage';

const GENERIC = { title: 'OneMind', body: 'Something new on your box. Open the app to see it.' };

/** Fetch the text for a ping and show it; the same identifier as the inbox refresh, so it never shows twice. */
export async function showPinged(api: OneMindApi, id: string | undefined): Promise<void> {
  if (!id) return showAlert({ id: 'ntf:ping', ...GENERIC, route: 'inbox' });
  try {
    const n = await api.notification(id);
    await showAlert({ id: `ntf:${n.id}`, title: n.title, body: n.body, route: n.action_id ? 'approvals' : 'inbox' });
  } catch {
    await showAlert({ id: `ntf:${id}`, ...GENERIC, route: 'inbox' });
  }
}

const LAST_PING = 'onemind.push.lastping.v1';

/** Remember that a ping reached this phone (only the time; the ping itself carries nothing else). */
export async function recordPing(now: number = Date.now()): Promise<void> {
  await saveSecret(LAST_PING, new Date(now).toISOString()).catch(() => undefined);
}

/**
 * When the last ping reached this phone: the newer of what the JavaScript saw and what the native
 * service saw while the app was closed. Settings shows it in place of a test button (the box has no
 * route that pings one device without filing anything).
 */
export async function lastPing(up: Pick<UnifiedPushNative, 'lastPingAt'> | undefined = unifiedPush): Promise<string | undefined> {
  const js = Date.parse((await loadSecret(LAST_PING)) ?? '');
  let native = 0;
  try {
    native = up?.lastPingAt?.() ?? 0;
  } catch {
    /* an older build without the function */
  }
  const t = Math.max(Number.isFinite(js) ? js : 0, native);
  return t > 0 ? new Date(t).toISOString() : undefined;
}

export function usePushPings(opts: {
  api: OneMindApi;
  hubUrl: string | undefined;
  label: string;
  /** `install_id` for a re-registration (lib/push installField): empty for a hub without My devices. */
  install?: { install_id?: string };
  reload: () => Promise<void>;
}) {
  const { api, hubUrl, label, reload } = opts;
  const installId = opts.install?.install_id;
  useEffect(() => {
    if (!hubUrl) return; // demo: no push
    const onPing = async (id: string | undefined) => {
      await recordPing();
      await reload();
      if (AppState.currentState !== 'active') await showPinged(api, id).catch(() => undefined);
    };
    const subs = [
      Notifications.addNotificationReceivedListener((n) => {
        const p = parsePing(n.request.content.data);
        if (p) void onPing(p.id);
      }),
    ];
    if (unifiedPush) {
      subs.push(unifiedPush.addListener('onMessage', (e) => void onPing(e.id ?? undefined)));
      subs.push(
        unifiedPush.addListener('onNewEndpoint', (e) => {
          void loadPushRecord(hubUrl).then((rec) => (rec ? rotateEndpoint(api, rec, e, label, installId ? { install_id: installId } : {}) : undefined)).catch(() => undefined);
        }),
      );
    }
    return () => subs.forEach((s) => s.remove());
  }, [api, hubUrl, label, installId, reload]);
}
