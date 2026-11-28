// SPDX-License-Identifier: Apache-2.0
import { Camera } from 'expo-camera';
import { permissionState } from './permission';

export { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';

export async function cameraPermission() {
  return permissionState(await Camera.getCameraPermissionsAsync());
}
