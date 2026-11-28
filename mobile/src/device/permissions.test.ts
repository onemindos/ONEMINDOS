// SPDX-License-Identifier: Apache-2.0
import { getRecordingPermissionsAsync, requestRecordingPermissionsAsync, setAudioModeAsync, useAudioPlayer, useAudioRecorder } from 'expo-audio';
import { Camera } from 'expo-camera';
import { getPermissionsAsync, requestPermissionsAsync } from 'expo-notifications';
import { getPermissionsAsync as getPhotoPermissions } from 'expo-media-library/legacy';
import { BackgroundTaskStatus, getStatusAsync } from 'expo-background-task';
import { backgroundPermission } from './background';
import { cameraPermission } from './camera';
import { photosPermission } from './files';
import { microphonePermission, usePlayback, useRecorder } from './mic';
import { allowNotifications, notificationPermission, requestNotificationPermission } from './notifications';

jest.mock('expo-audio', () => ({
  getRecordingPermissionsAsync: jest.fn(), requestRecordingPermissionsAsync: jest.fn(), setAudioModeAsync: jest.fn(),
  useAudioRecorder: jest.fn(), useAudioPlayer: jest.fn(), RecordingPresets: { HIGH_QUALITY: {} },
}));
jest.mock('expo-camera', () => ({ Camera: { getCameraPermissionsAsync: jest.fn() } }));
jest.mock('expo-media-library/legacy', () => ({ getPermissionsAsync: jest.fn() }));
jest.mock('expo-background-task', () => ({ BackgroundTaskStatus: { Available: 2, Restricted: 1 }, getStatusAsync: jest.fn() }));

function result(granted: boolean, canAskAgain = true) {
  return { granted, canAskAgain, status: (granted ? 'granted' : 'denied') as never, expires: 'never' as const };
}

beforeEach(() => jest.clearAllMocks());

it.each([
  [cameraPermission, Camera.getCameraPermissionsAsync],
  [microphonePermission, getRecordingPermissionsAsync],
  [notificationPermission, getPermissionsAsync],
  [photosPermission, getPhotoPermissions],
] as const)('reads a grant, denial and a subsequent revocation from the OS', async (read, native) => {
  const query = native as jest.Mock;
  query.mockResolvedValueOnce(result(true)).mockResolvedValueOnce(result(false)).mockResolvedValueOnce(result(false, false));
  await expect(read()).resolves.toBe('Allowed');
  await expect(read()).resolves.toBe('Denied');
  await expect(read()).resolves.toBe('Blocked');
  expect(requestRecordingPermissionsAsync).not.toHaveBeenCalled();
  expect(requestPermissionsAsync).not.toHaveBeenCalled();
});

it('reports limited photo access and background restrictions', async () => {
  jest.mocked(getPhotoPermissions).mockResolvedValue({ ...result(true), accessPrivileges: 'limited' });
  await expect(photosPermission()).resolves.toBe('Selected items only');
  jest.mocked(getStatusAsync).mockResolvedValueOnce(BackgroundTaskStatus.Available)
    .mockResolvedValueOnce(BackgroundTaskStatus.Restricted);
  await expect(backgroundPermission()).resolves.toBe('Available');
  await expect(backgroundPermission()).resolves.toBe('Restricted');
  jest.mocked(getStatusAsync).mockResolvedValueOnce(99 as never);
  await expect(backgroundPermission()).resolves.toBe('Unavailable');
});

it('the Settings button asks when it can, and opens phone settings when the system blocked the prompt', async () => {
  const openSettings = jest.fn(async () => undefined);
  jest.mocked(getPermissionsAsync).mockResolvedValueOnce(result(false)).mockResolvedValueOnce(result(false, false));
  jest.mocked(requestPermissionsAsync).mockResolvedValueOnce(result(true));
  await expect(allowNotifications(openSettings)).resolves.toBe(true);
  expect(openSettings).not.toHaveBeenCalled();
  await expect(allowNotifications(openSettings)).resolves.toBe(false);
  expect(openSettings).toHaveBeenCalledTimes(1);
  expect(requestPermissionsAsync).toHaveBeenCalledTimes(1);
});

it('only starts recording after a grant and checks the permission again after revocation', async () => {
  const recorder = { prepareToRecordAsync: jest.fn(), record: jest.fn(), stop: jest.fn(), uri: 'file:///take.m4a' };
  jest.mocked(useAudioRecorder).mockReturnValue(recorder as never);
  jest.mocked(getRecordingPermissionsAsync).mockResolvedValueOnce(result(false)).mockResolvedValueOnce(result(false, false));
  jest.mocked(requestRecordingPermissionsAsync).mockResolvedValueOnce(result(true));
  const mic = useRecorder();
  await expect(mic.start()).resolves.toBe('Allowed');
  await expect(mic.stop()).resolves.toBe('file:///take.m4a');
  await expect(mic.start()).resolves.toBe('Blocked');
  expect(recorder.record).toHaveBeenCalledTimes(1);
  expect(setAudioModeAsync).toHaveBeenLastCalledWith({ allowsRecording: false });
});

it('asks for notifications only on an explicit request and respects the OS block', async () => {
  jest.mocked(getPermissionsAsync).mockResolvedValueOnce(result(false)).mockResolvedValueOnce(result(false, false));
  jest.mocked(requestPermissionsAsync).mockResolvedValueOnce(result(true));
  await expect(requestNotificationPermission()).resolves.toBe(true);
  await expect(requestNotificationPermission()).resolves.toBe(false);
  expect(requestPermissionsAsync).toHaveBeenCalledTimes(1);
});

it('plays a recording without asking to use the microphone', () => {
  const player = { play: jest.fn(), pause: jest.fn() };
  jest.mocked(useAudioPlayer).mockReturnValue(player as never);
  const playback = usePlayback('file:///take.m4a');
  playback.play();
  playback.pause();
  expect(player.play).toHaveBeenCalledTimes(1);
  expect(player.pause).toHaveBeenCalledTimes(1);
  expect(requestRecordingPermissionsAsync).not.toHaveBeenCalled();
});
