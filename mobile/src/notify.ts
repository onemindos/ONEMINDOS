// SPDX-License-Identifier: Apache-2.0
// Local notifications (expo-notifications): what the app shows itself, with text it read from the
// box over HTTPS. Remote pings (mobile/docs/push.md) carry no text; while the app is open their
// generic banner is suppressed and the app shows the real text instead.
import { Notifications } from './device/notifications';
import { Platform } from 'react-native';
import { unifiedPush } from '../modules/onemind-unifiedpush';
import type { Alert } from './lib/alerts';
import { parsePing } from './lib/push';
import { ACTION_DENY, ACTION_REVIEW, APPROVAL_CATEGORY } from './lock/actions';

let configured = false;

/**
 * The buttons on an approval notification (issue #704): Review and Deny, both needing the phone
 * unlocked (iOS authenticationRequired; on Android expo-notifications cannot set it, so approvals are
 * shown by the native module with setAuthenticationRequired, and Deny also asks for an in-app unlock
 * before it records anything). Approve is never a notification button.
 */
export const APPROVAL_ACTIONS: Notifications.NotificationAction[] = [
  { identifier: ACTION_REVIEW, buttonTitle: 'Review', options: { opensAppToForeground: true, isAuthenticationRequired: true } },
  { identifier: ACTION_DENY, buttonTitle: 'Deny', options: { opensAppToForeground: true, isAuthenticationRequired: true, isDestructive: true } },
];

export async function setupNotifications(): Promise<boolean> {
  if (!configured) {
    configured = true;
    Notifications.setNotificationHandler({
      handleNotification: async (n) => {
        const ping = parsePing(n.request.content.data) !== undefined;
        return { shouldShowBanner: !ping, shouldShowList: !ping, shouldPlaySound: false, shouldSetBadge: false };
      },
    });
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('hub', {
        name: 'Hub activity',
        importance: Notifications.AndroidImportance.HIGH,
      });
    } else if (Platform.OS === 'ios') {
      await Notifications.setNotificationCategoryAsync(APPROVAL_CATEGORY, APPROVAL_ACTIONS).catch(() => null);
    }
  }
  return (await Notifications.getPermissionsAsync()).granted;
}

export async function showAlert(a: Alert): Promise<void> {
  const actionId = a.route === 'approvals' ? a.actionId : undefined;
  if (actionId && Platform.OS === 'android' && unifiedPush?.showApproval) {
    unifiedPush.showApproval(a.id, a.title, a.body, actionId);
    return;
  }
  await Notifications.scheduleNotificationAsync({
    identifier: a.id,
    content: {
      title: a.title,
      body: a.body,
      data: actionId ? { route: a.route, action_id: actionId } : { route: a.route },
      ...(actionId && Platform.OS === 'ios' ? { categoryIdentifier: APPROVAL_CATEGORY } : {}),
    },
    trigger: Platform.OS === 'android' ? { channelId: 'hub' } : null,
  });
}

export async function setBadge(n: number): Promise<void> {
  try {
    await Notifications.setBadgeCountAsync(n);
  } catch {
    /* not supported on this launcher */
  }
}
