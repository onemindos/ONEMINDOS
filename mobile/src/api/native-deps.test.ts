// SPDX-License-Identifier: Apache-2.0
// Wave P native modules (#233): the camera (join-code scanning) and the biometric check before an
// approval. They are added once here, with their permissions, so the screens that use them do not
// edit package.json or app.json. The release build fails on any permission app.json blocks
// (scripts/android-release-build.sh), so USE_BIOMETRIC must not be blocked any more.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { expo } = require('../../app.json') as {
  expo: {
    android: { permissions: string[]; blockedPermissions: string[] };
    ios: { infoPlist: Record<string, unknown> };
    plugins: Array<string | [string, Record<string, unknown>]>;
  };
};
// eslint-disable-next-line @typescript-eslint/no-require-imports
const pkg = require('../../package.json') as { dependencies: Record<string, string> };

const plugin = (name: string) => expo.plugins.find((p) => (Array.isArray(p) ? p[0] : p) === name);

it('ships expo-camera and expo-local-authentication at exact versions', () => {
  expect(pkg.dependencies['expo-camera']).toMatch(/^\d+\.\d+\.\d+$/);
  expect(pkg.dependencies['expo-local-authentication']).toMatch(/^\d+\.\d+\.\d+$/);
});

it('asks for the camera without the microphone', () => {
  expect(expo.android.permissions).toContain('android.permission.CAMERA');
  const cam = plugin('expo-camera') as [string, Record<string, unknown>];
  expect(typeof cam[1].cameraPermission).toBe('string');
  expect(cam[1].recordAudioAndroid).toBe(false);
});

it('declares microphone access for Recorder and explains location access on iOS', () => {
  expect(expo.ios.infoPlist.NSMicrophoneUsageDescription).toContain('Recorder');
  expect(expo.ios.infoPlist.NSLocationWhenInUseUsageDescription).toContain('when you ask');
  const [, audio] = plugin('expo-audio') as [string, Record<string, unknown>];
  expect(audio.enableBackgroundRecording).toBe(false);
  expect(audio.enableBackgroundPlayback).toBe(false);
});

it('allows the biometric prompt (USE_BIOMETRIC) and explains Face ID', () => {
  expect(expo.android.permissions).toContain('android.permission.USE_BIOMETRIC');
  expect(expo.android.blockedPermissions).not.toContain('android.permission.USE_BIOMETRIC');
  const la = plugin('expo-local-authentication') as [string, Record<string, unknown>];
  expect(typeof la[1].faceIDPermission).toBe('string');
});
