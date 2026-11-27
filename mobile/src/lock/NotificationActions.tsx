// SPDX-License-Identifier: Apache-2.0
// Where notification taps, Review/Deny buttons and the closed-app Deny links land (issue #704).
// A tap or Review opens the app there. Deny asks for an unlock, then records the deny on the box.
// Nothing here can approve.
import * as Notifications from 'expo-notifications';
import { useEffect, useRef } from 'react';
import { Alert, Linking } from 'react-native';
import { useHubData } from '../data';
import { useSignedIn } from '../session';
import { denyAfterUnlock, parseDenyLink, responseIntent, type DenyTarget, type ResponseLike } from './actions';
import { useLock } from './LockProvider';

// Kept for the life of the process, not of the component: SignedIn mounts again on a hub switch or a
// sign-out and in, and the launch URL and the last notification response would otherwise be replayed
// as a new Deny prompt.
const handledResponses = new Set<string>();
const handledInitialUrls = new Set<string>();

export function NotificationActions({ open }: { open: (data: Record<string, unknown> | undefined) => void }) {
  const { api } = useSignedIn();
  const { reload } = useHubData();
  const { confirm } = useLock();
  const ref = useRef({ api, reload, confirm, open });
  ref.current = { api, reload, confirm, open };

  useEffect(() => {
    const deny = async (target: DenyTarget): Promise<string> => {
      const { api: a, confirm: c, reload: r } = ref.current;
      const res = await denyAfterUnlock(a, target, c);
      if (res.outcome === 'denied') void r().catch(() => undefined);
      if (res.outcome !== 'cancelled') Alert.alert(res.outcome === 'denied' ? 'Denied' : 'Deny', res.message);
      return res.outcome;
    };
    const onResponse = (r: ResponseLike) => {
      const key = `${r.notification.request.identifier}:${r.actionIdentifier}`;
      if (handledResponses.has(key)) return;
      handledResponses.add(key);
      const intent = responseIntent(r);
      if (intent.kind === 'deny') {
        // A cancelled unlock must not block a later Deny on the same notification.
        void deny(intent.target).then((outcome) => {
          if (outcome === 'cancelled') handledResponses.delete(key);
        });
      }
      else ref.current.open(intent.data);
    };
    const onUrl = (url: string | null | undefined) => {
      const target = parseDenyLink(url);
      if (target) void deny(target);
    };
    const subs = [
      Notifications.addNotificationResponseReceivedListener(onResponse),
      Linking.addEventListener('url', (e) => onUrl(e.url)),
    ];
    // Opened from a notification or a Deny link while the app was not running.
    void Notifications.getLastNotificationResponseAsync()
      .then((r) => {
        if (!r) return;
        onResponse(r);
        Notifications.clearLastNotificationResponse?.();
      })
      .catch(() => undefined);
    void Linking.getInitialURL()
      .then((url) => {
        if (!url || handledInitialUrls.has(url)) return;
        handledInitialUrls.add(url);
        onUrl(url);
      })
      .catch(() => undefined);
    return () => subs.forEach((s) => s.remove());
  }, []);
  return null;
}
