// SPDX-License-Identifier: Apache-2.0
import { BackgroundTask, TaskManager } from '../device/background';
import { HttpApi } from '../api/client';
import { loadConnection } from '../storage';
import { deliverShare, readShare, shareDirectory } from './shareQueue';

const TASK = 'onemind-incoming-files';

TaskManager.defineTask(TASK, async () => {
  try {
    const connection = await loadConnection();
    if (connection?.mode !== 'live') return BackgroundTask.BackgroundTaskResult.Success;
    const api = new HttpApi({ baseUrl: connection.hubUrl, token: connection.token });
    const { principal } = await api.me();
    if (principal.kind !== 'person') return BackgroundTask.BackgroundTaskResult.Success;
    const dir = await shareDirectory(connection.hubUrl, principal.id);
    const job = await readShare(dir);
    if (!job) await unscheduleShare();
    else if (!job.error) await deliverShare(api, dir);
    return BackgroundTask.BackgroundTaskResult.Success;
  } catch {
    return BackgroundTask.BackgroundTaskResult.Failed;
  }
});

export async function scheduleShare() {
  if (!(await TaskManager.isTaskRegisteredAsync(TASK))) {
    await BackgroundTask.registerTaskAsync(TASK, { minimumInterval: 15 });
  }
}

export async function unscheduleShare() {
  if (await TaskManager.isTaskRegisteredAsync(TASK)) await BackgroundTask.unregisterTaskAsync(TASK);
}
