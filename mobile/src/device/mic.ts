// SPDX-License-Identifier: Apache-2.0
import {
  getRecordingPermissionsAsync, RecordingPresets, requestRecordingPermissionsAsync,
  setAudioModeAsync, useAudioPlayer, useAudioRecorder,
} from 'expo-audio';
import { permissionState } from './permission';

export async function microphonePermission() {
  return permissionState(await getRecordingPermissionsAsync());
}

export function useRecorder() {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  return {
    async start() {
      const current = await getRecordingPermissionsAsync();
      const permission = !current.granted && current.canAskAgain ? await requestRecordingPermissionsAsync() : current;
      if (!permission.granted) return permissionState(permission);
      await setAudioModeAsync({ allowsRecording: true, allowsBackgroundRecording: false });
      try {
        await recorder.prepareToRecordAsync();
        recorder.record();
        return 'Allowed';
      } catch (error) {
        await setAudioModeAsync({ allowsRecording: false });
        throw error;
      }
    },
    async stop() {
      try {
        await recorder.stop();
        return recorder.uri;
      } finally {
        await setAudioModeAsync({ allowsRecording: false });
      }
    },
  };
}

export function usePlayback(uri: string | null) {
  const player = useAudioPlayer(uri);
  return { play: () => player.play(), pause: () => player.pause() };
}
