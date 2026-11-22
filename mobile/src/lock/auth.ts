// SPDX-License-Identifier: Apache-2.0
// The phone's own unlock (face, fingerprint or the screen-lock PIN) through expo-local-authentication.
// It guards what this app shows and what a lock-screen Deny does; it never guards a stored token, so
// background photo backup and push keep working while the app is locked (issue #704).
import * as LocalAuthentication from 'expo-local-authentication';

let inflight: Promise<boolean> | undefined;

/** True when the phone has a screen lock or biometrics set up, so Lock OneMind can be turned on. */
export async function lockAvailable(): Promise<boolean> {
  try {
    return (await LocalAuthentication.getEnrolledLevelAsync()) > LocalAuthentication.SecurityLevel.NONE;
  } catch {
    return false;
  }
}

/**
 * Ask the person to unlock. Only one prompt at a time: a second caller (say, the app lock and a
 * lock-screen Deny arriving together) shares the answer to the prompt already on screen.
 */
export function authenticate(promptMessage: string): Promise<boolean> {
  if (inflight) return inflight;
  inflight = LocalAuthentication.authenticateAsync({ promptMessage, cancelLabel: 'Cancel' })
    .then((r) => r.success)
    .catch(() => false)
    .finally(() => {
      inflight = undefined;
    });
  return inflight;
}
