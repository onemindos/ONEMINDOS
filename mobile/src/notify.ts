// SPDX-License-Identifier: Apache-2.0
// Local notifications (expo-notifications): what the app shows itself, with text it read from the
// box over HTTPS. Remote pings (mobile/docs/push.md) carry no text; while the app is open their
// generic banner is suppressed and the app shows the real text instead.
import { Notifications } from './device/notifications';
import { Platform } from 'react-native';
import type { Alert } from './lib/alerts';
import { parsePing } from './lib/push';

let configured = false;

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
    }
  }
  return (await Notifications.getPermissionsAsync()).granted;
}

export async function showAlert(a: Alert): Promise<void> {
  await Notifications.scheduleNotificationAsync({
    identifier: a.id,
    content: { title: a.title, body: a.body, data: { route: a.route } },
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
