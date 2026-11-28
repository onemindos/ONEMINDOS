// SPDX-License-Identifier: Apache-2.0
import * as BackgroundTask from 'expo-background-task';
import * as TaskManager from 'expo-task-manager';

export { BackgroundTask, TaskManager };

export async function backgroundPermission(): Promise<string> {
  const status = await BackgroundTask.getStatusAsync();
  if (status === BackgroundTask.BackgroundTaskStatus.Available) return 'Available';
  if (status === BackgroundTask.BackgroundTaskStatus.Restricted) return 'Restricted';
  return 'Unavailable';
}
