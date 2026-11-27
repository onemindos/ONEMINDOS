// SPDX-License-Identifier: Apache-2.0
// The phone's own unlock (face, fingerprint or the screen-lock PIN) through expo-local-authentication.
// It guards what this app shows and what a lock-screen Deny does; it never guards a stored token, so
// background photo backup and push keep working while the app is locked (issue #704).
import * as LocalAuthentication from 'expo-local-authentication';

let inflight: { message: string; result: Promise<boolean> } | undefined;

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
export function authenticate(promptMessage: string): Promise<boolean> {
  if (inflight && inflight.message === promptMessage) return inflight.result;
  const prior = inflight?.result.catch(() => false) ?? Promise.resolve(false);
  const result: Promise<boolean> = prior
    .then(() => LocalAuthentication.authenticateAsync({ promptMessage, cancelLabel: 'Cancel' }))
    .then((r) => r.success)
    .catch(() => false)
    .finally(() => {
      if (inflight?.result === result) inflight = undefined;
    });
  inflight = { message: promptMessage, result };
  return result;
}
