// SPDX-License-Identifier: Apache-2.0
import * as Notifications from 'expo-notifications';
import { permissionState } from './permission';

export { Notifications };

export async function notificationPermission() {
  return permissionState(await Notifications.getPermissionsAsync());
}

export async function requestNotificationPermission(): Promise<boolean> {
  const current = await Notifications.getPermissionsAsync();
  return current.granted || (current.canAskAgain && (await Notifications.requestPermissionsAsync()).granted);
}
