// SPDX-License-Identifier: Apache-2.0
// Background backup through expo-background-task (iOS BGTaskScheduler, Android WorkManager).
// The OS decides when this runs (at best every 15 minutes, usually less often, typically while
// charging on Wi-Fi). Each run uploads chunks until the OS ends its time or the deadline passes,
// and the next run continues from the box's offset. Must be imported from index.ts so the task is
// defined before the OS can launch the app headless.
import * as BackgroundTask from 'expo-background-task';
import * as TaskManager from 'expo-task-manager';
import { HttpApi } from '../api/client';
import { loadConnection } from '../storage';
import { discoverPhotos } from './discovery';
import { runBackup } from './engine';
import { ExpoMedia, FileStore, PLATFORM, readConditions } from './native';
import { HttpPhotosApi } from './protocol';

export const PHOTO_TASK = 'onemind-photo-backup';
/** Upper bound for one background run; the OS may end it sooner (expiration listener). */
const BACKGROUND_BUDGET_MS = 8 * 60_000;

TaskManager.defineTask(PHOTO_TASK, async () => {
  try {
    const conn = await loadConnection();
    if (!conn || conn.mode !== 'live') return BackgroundTask.BackgroundTaskResult.Success;
    const store = new FileStore();
    const settings = await store.loadSettings();
    if (!settings.enabled) return BackgroundTask.BackgroundTaskResult.Success;
    const apps = await new HttpApi({ baseUrl: conn.hubUrl, token: conn.token }).apps();
    const av = discoverPhotos(conn, apps, '');
    if (av.state !== 'ok') return BackgroundTask.BackgroundTaskResult.Success;
    const signal = { aborted: false };
    const sub = BackgroundTask.addExpirationListener(() => {
      signal.aborted = true;
    });
    try {
      await runBackup({
        api: new HttpPhotosApi({ baseUrl: av.baseUrl, token: conn.token }),
        media: new ExpoMedia(),
        store,
        settings,
        conditions: readConditions,
        platform: PLATFORM,
        deviceName: PLATFORM === 'ios' ? 'iPhone' : 'Android phone',
        trigger: 'background',
        deadline: Date.now() + BACKGROUND_BUDGET_MS,
        signal,
      });
    } finally {
      sub.remove();
    }
    return BackgroundTask.BackgroundTaskResult.Success;
  } catch {
    return BackgroundTask.BackgroundTaskResult.Failed;
  }
});

export async function setBackgroundBackup(on: boolean): Promise<'available' | 'restricted' | 'unknown'> {
  try {
    const status = await BackgroundTask.getStatusAsync();
    const registered = await TaskManager.isTaskRegisteredAsync(PHOTO_TASK);
    if (on && status === BackgroundTask.BackgroundTaskStatus.Available && !registered)
      await BackgroundTask.registerTaskAsync(PHOTO_TASK, { minimumInterval: 15 });
    if (!on && registered) await BackgroundTask.unregisterTaskAsync(PHOTO_TASK);
    return status === BackgroundTask.BackgroundTaskStatus.Available ? 'available' : 'restricted';
  } catch {
    return 'unknown';
  }
}
