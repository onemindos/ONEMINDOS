// SPDX-License-Identifier: Apache-2.0
// The phone's own unlock (face, fingerprint or the screen-lock PIN) through expo-local-authentication.
// It guards what this app shows and what a lock-screen Deny does; it never guards a stored token, so
// background photo backup and push keep working while the app is locked (issue #704).
import * as LocalAuthentication from 'expo-local-authentication';

let lastPrompt: Promise<boolean> = Promise.resolve(false);
const inflight = new Map<string | symbol, Promise<boolean>>();

/** True when the phone has a screen lock or biometrics set up, so Lock OneMind can be turned on. */
export async function lockAvailable(): Promise<boolean> {
  try {
    return (await LocalAuthentication.getEnrolledLevelAsync()) > LocalAuthentication.SecurityLevel.NONE;
  } catch {
    return false;
  }
}

/**
 * Ask the person to unlock. The same question asked twice at once shares one prompt. A different
 * question (a lock-screen Deny arriving while "Unlock OneMind" is on screen) waits for that prompt
 * and then asks its own, so a Deny is never confirmed by an answer to another question.
 */
export function authenticate(
  promptMessage: string,
  key: string | symbol = promptMessage,
  promptDescription?: string,
): Promise<boolean> {
  const existing = inflight.get(key);
  if (existing) return existing;
  const result = lastPrompt
    .then(() => LocalAuthentication.authenticateAsync({ promptMessage, promptDescription, cancelLabel: 'Cancel' }))
    .then((r) => r.success)
    .catch(() => false)
    .finally(() => inflight.delete(key));
  inflight.set(key, result);
  lastPrompt = result;
  return result;
}
