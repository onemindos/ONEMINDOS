// SPDX-License-Identifier: Apache-2.0
// Where notification taps, Review/Deny buttons and the closed-app Deny links land (issue #704).
// A tap or Review opens the app there. Deny asks for an unlock, then records the deny on the box.
// Nothing here can approve.
import * as Notifications from 'expo-notifications';
import { useEffect, useRef } from 'react';
import { Alert, Linking } from 'react-native';
import { useHubData } from '../data';
import { useSignedIn } from '../session';
import { denyAfterUnlock, isRequestId, parseDenyLink, parseReviewLink, resolveApprovalTarget, responseIntent, type ApprovalTarget, type ResponseLike } from './actions';
import { useLock } from './LockProvider';

// Kept for the life of the process, not of the component: SignedIn mounts again on a hub switch or a
// sign-out and in, and the launch URL and the last notification response would otherwise be replayed
// as a new Deny prompt.
const handledResponses = new Map<string, 'handled' | 'retry'>();
const handledInitialUrls = new Set<string>();

export function NotificationActions({ open }: { open: (data: Record<string, unknown> | undefined) => void }) {
  const { api } = useSignedIn();
  const { reload } = useHubData();
  const { confirm } = useLock();
  const ref = useRef({ api, reload, confirm, open });
  ref.current = { api, reload, confirm, open };

  useEffect(() => {
    let live = true;
    const deny = async (target: ApprovalTarget) => {
      const { api: a, confirm: c, reload: r } = ref.current;
      const res = await denyAfterUnlock(a, target, async (reason, id) => live && await c(reason, id) && live);
      if (live) {
        if (res.outcome === 'denied') void r().catch(() => undefined);
        if (res.outcome !== 'cancelled') Alert.alert(res.outcome === 'denied' ? 'Denied' : 'Deny', res.message);
      }
      return res.outcome;
    };
    const onResponse = (r: ResponseLike, warm: boolean) => {
      const key = `${r.notification.request.identifier}:${r.actionIdentifier}`;
      if (!live) return;
      // Expo caches warm taps too. Remember consumed keys even if an older native build cannot clear.
      try { Notifications.clearLastNotificationResponse(); } catch { /* native method unavailable */ }
      const previous = handledResponses.get(key);
      const intent = responseIntent(r);
      if (previous && (!warm || (intent.kind === 'deny' && previous === 'handled'))) return;
      handledResponses.set(key, 'handled');
      if (intent.kind === 'deny') {
        // Keep the cached response consumed, but let a fresh tap retry a failed attempt.
        void deny(intent.target).then((outcome) => {
          if (outcome === 'cancelled' || outcome === 'failed') handledResponses.set(key, 'retry');
        });
      } else {
        ref.current.open(intent.data);
        if (intent.data?.route === 'approvals' && isRequestId(intent.data.action_id)) {
          void ref.current.reload().catch(() => undefined);
        }
      }
    };
    const review = async (target: ApprovalTarget) => {
      const a = ref.current.api;
      const actionId = await resolveApprovalTarget(a, target).catch(() => undefined);
      if (!live) return;
      if (actionId) {
        ref.current.open({ route: 'approvals', action_id: actionId });
        void ref.current.reload().catch(() => undefined);
      } else if ('notificationId' in target) {
        ref.current.open({ route: 'inbox', notification_id: target.notificationId });
      }
    };
    const onUrl = (url: string | null | undefined) => {
      if (!live) return;
      const target = parseDenyLink(url);
      if (target) void deny(target);
      else {
        const requested = parseReviewLink(url);
        if (requested) void review(requested);
      }
    };
    const subs = [
      Notifications.addNotificationResponseReceivedListener((r) => onResponse(r, true)),
      Linking.addEventListener('url', (e) => onUrl(e.url)),
    ];
    // Opened from a notification or a native link while the app was not running.
    void Notifications.getLastNotificationResponseAsync()
      .then((r) => { if (r) onResponse(r, false); })
      .catch(() => undefined);
    void Linking.getInitialURL()
      .then((url) => {
        if (!live || !url || handledInitialUrls.has(url)) return;
        handledInitialUrls.add(url);
        onUrl(url);
      })
      .catch(() => undefined);
    return () => {
      live = false;
      subs.forEach((s) => s.remove());
    };
  }, []);
  return null;
}
