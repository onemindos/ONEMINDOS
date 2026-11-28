// SPDX-License-Identifier: Apache-2.0
import { requireNativeModule } from 'expo';
import { AppState } from 'react-native';
import { permissionState } from './permission';

type LocationGrant = { granted: boolean; canAskAgain: boolean; status: string };
export type PhonePosition = { latitude: number; longitude: number; accuracyMeters: number; timestamp: number };
type LocationAdapter = {
  getPermission(background: boolean): Promise<LocationGrant>;
  requestPermission(background: boolean): Promise<LocationGrant>;
  currentPosition(background: boolean): Promise<PhonePosition>;
};
const adapter = () => requireNativeModule<LocationAdapter>('OneMindLocation');

export async function locationPermission(background = false) {
  if (background) return 'Not available';
  return permissionState(await adapter().getPermission(background));
}

export async function requestLocationPermission(options: { background?: boolean } = {}) {
  if (options.background) return 'Not available';
  const location = adapter();
  const current = await location.getPermission(false);
  if (!current.granted && current.canAskAgain) await location.requestPermission(false);
  // On Android 12+ the person may grant approximate access while denying precise access.
  return permissionState(await location.getPermission(false));
}

export async function currentPosition(options: { background?: boolean } = {}): Promise<PhonePosition> {
  if (options.background) throw new Error('Background location is not available.');
  if (AppState.currentState !== 'active') throw new Error('Open OneMind to use location.');
  const location = adapter();
  if (!(await location.getPermission(false)).granted) throw new Error('Location access is off.');
  return location.currentPosition(false);
}
