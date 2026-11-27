// SPDX-License-Identifier: Apache-2.0
import { ApiError } from '../api/types';

/** Plain words for why adding or removing a key did not happen. */
export function keyErrorText(e: unknown): string {
  if (e instanceof ApiError && e.reason === 'verification_level_unmet') return 'this needs your proven key, and none of your keys is one yet';
  if (e instanceof ApiError && e.reason === 'box_code_required') return 'the code from the box\'s own screen was missing or wrong, so nothing changed. Ask again: the box shows a new code each time';
  if (e instanceof ApiError && e.reason === 'box_code_locked') return 'too many wrong codes from the box\'s screen; wait 15 minutes, then try again';
  if (e instanceof ApiError && e.reason === 'box_presence_unavailable') return 'this box has no screen to show a confirmation code, so this waits for a proven key';
  if (e instanceof ApiError && e.reason === 'cancelled') return 'cancelled, so nothing changed';
  // The hub named no step-up the page could make in place (an older hub), or the check did not finish.
  if (e instanceof ApiError && e.reason === 'step_up_required') return 'the hub needs a fresh check. Sign out, sign in again with your passkey or with your password and authenticator code, then do this again';
  if (e instanceof Error && e.name === 'NotAllowedError') return 'the passkey check was cancelled or timed out, so nothing changed';
  return e instanceof Error ? e.message : String(e);
}
