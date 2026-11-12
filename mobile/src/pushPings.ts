// SPDX-License-Identifier: Apache-2.0
// What the app does when a ping from the box arrives while its JavaScript runs (mobile/docs/push.md §5):
// refresh from the box, and when the app is not on screen, show the text it fetched over HTTPS.
import * as Notifications from 'expo-notifications';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { unifiedPush } from '../modules/onemind-unifiedpush';
import type { OneMindApi } from './api/client';
import { loadPushRecord, parsePing, rotateEndpoint } from './lib/push';
import { showAlert } from './notify';

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

export function usePushPings(opts: { api: OneMindApi; hubUrl: string | undefined; label: string; reload: () => Promise<void> }) {
  const { api, hubUrl, label, reload } = opts;
  useEffect(() => {
    if (!hubUrl) return; // demo: no push
    const onPing = async (id: string | undefined) => {
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
          void loadPushRecord(hubUrl).then((rec) => (rec ? rotateEndpoint(api, rec, e, label) : undefined)).catch(() => undefined);
        }),
      );
    }
    return () => subs.forEach((s) => s.remove());
  }, [api, hubUrl, label, reload]);
}
