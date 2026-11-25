// SPDX-License-Identifier: Apache-2.0
// The client protocol policy for the phone app (sdk/contracts/protocol-versions.md, issue 697).
// The app declares its generation on every request; once any answer says the hub no longer serves
// it, the app shows "Update needed" instead of screens that may misread the hub's answers.
// The values match @onemind/sdk (src/lib/protocol.test.ts checks them against the OpenAPI contract).
import { useSyncExternalStore } from 'react';

export const PROTOCOL_HEADER = 'X-OneMind-Protocol';
export const PROTOCOL_MIN_HEADER = 'X-OneMind-Protocol-Min';
export const PROTOCOL_MAX_HEADER = 'X-OneMind-Protocol-Max';
export const BUILT_IN_PROTOCOL = 2;

/**
 * What this build speaks. EXPO_PUBLIC_ONEMIND_PROTOCOL (inlined at build time) may only lower it,
 * so a lab kit can build "an older app" and prove the Update needed screen on a real phone.
 */
export function protocolVersion(override: string | undefined = process.env.EXPO_PUBLIC_ONEMIND_PROTOCOL): number {
  const n = Number(override);
  return override && Number.isInteger(n) && n >= 1 && n <= BUILT_IN_PROTOCOL ? n : BUILT_IN_PROTOCOL;
}

export const PROTOCOL_VERSION = protocolVersion();

export interface UpdateNeeded { sent: number; min: number; max: number }

let state: UpdateNeeded | null = null;
const listeners = new Set<() => void>();

/** Reads the range from one answer; flips the app to "Update needed" when this build is below it. */
export function noteProtocol(headers: Headers, version: number = PROTOCOL_VERSION): void {
  const min = Number(headers.get(PROTOCOL_MIN_HEADER));
  const max = Number(headers.get(PROTOCOL_MAX_HEADER));
  if (!Number.isInteger(min) || !Number.isInteger(max) || min < 1 || max < min) return; // a hub from before the headers
  if (version >= min || state) return;
  state = { sent: version, min, max };
  listeners.forEach((l) => l());
}

export function useUpdateNeeded(): UpdateNeeded | null {
  return useSyncExternalStore((l) => (listeners.add(l), () => listeners.delete(l)), () => state);
}

/** Tests only: forget a previous "Update needed". */
export function resetProtocolState(): void {
  state = null;
  listeners.forEach((l) => l());
}
