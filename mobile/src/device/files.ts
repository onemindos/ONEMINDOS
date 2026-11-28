// SPDX-License-Identifier: Apache-2.0
import * as DocumentPicker from 'expo-document-picker';
import * as MediaLibrary from 'expo-media-library/legacy';
import * as Sharing from 'expo-sharing';
import { permissionState } from './permission';

export { Directory, File, FileMode, Paths } from 'expo-file-system';
export type { ResolvedSharePayload, SharePayload } from 'expo-sharing';
export { DocumentPicker, MediaLibrary, Sharing };

export async function photosPermission(): Promise<string> {
  const current = await MediaLibrary.getPermissionsAsync(false, ['photo', 'video']);
  return current.accessPrivileges === 'limited' ? 'Selected items only' : permissionState(current);
}
