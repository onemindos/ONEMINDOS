// SPDX-License-Identifier: Apache-2.0
import { Linking } from 'react-native';
import * as Notifications from 'expo-notifications';
import { permissionState } from './permission';

export { Notifications };

export async function notificationPermission() {
  return permissionState(await Notifications.getPermissionsAsync());
}

/** The Settings button: ask; when the OS will not show the prompt again, open the phone's settings instead. */
export async function allowNotifications(openSettings: () => Promise<void> = () => Linking.openSettings()): Promise<boolean> {
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  if (!current.canAskAgain) {
    await openSettings();
    return false;
  }
  return (await Notifications.requestPermissionsAsync()).granted;
}

export async function requestNotificationPermission(): Promise<boolean> {
  const current = await Notifications.getPermissionsAsync();
  return current.granted || (current.canAskAgain && (await Notifications.requestPermissionsAsync()).granted);
}
