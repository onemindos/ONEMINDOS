// SPDX-License-Identifier: Apache-2.0
// What the Backup screens read. Kept apart from controller.tsx so screens and their tests do not
// load any native module.
import { createContext, useContext } from 'react';
import type { Availability } from './discovery';
import type { Conditions, Progress } from './engine';
import type { BackupSettings, Ledger } from './ledger';
import type { MediaAlbum, MediaPermission } from './media';

export type BackgroundState = 'available' | 'restricted' | 'unknown' | 'demo';

export interface PhotoBackupState {
  availability: Availability;
  settings: BackupSettings;
  ledger: Ledger | null;
  permission: MediaPermission | undefined;
  conditions: Conditions | undefined;
  background: BackgroundState;
  running: boolean;
  progress?: Progress;
  albums?: MediaAlbum[];
  /** Host that receives uploads (shown so the person knows where photos go). */
  host?: string;
  demo: boolean;
  runNow(): Promise<void>;
  stop(): void;
  updateSettings(patch: Partial<BackupSettings>): Promise<void>;
  requestPermission(): Promise<void>;
  loadAlbums(): Promise<void>;
}

export const PhotoBackupContext = createContext<PhotoBackupState | null>(null);

export function usePhotoBackup(): PhotoBackupState {
  const c = useContext(PhotoBackupContext);
  if (!c) throw new Error('usePhotoBackup outside PhotoBackupProvider');
  return c;
}
