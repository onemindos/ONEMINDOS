// SPDX-License-Identifier: Apache-2.0
// The client protocol policy for the dashboard (sdk/contracts/protocol-versions.md, issue 697).
// Every answer from the hub carries the generations it serves; once one says this build is too old,
// the whole app shows "Update needed" instead of screens that may misread the hub's answers.
import { useSyncExternalStore } from 'react';
import { PROTOCOL_HEADER, PROTOCOL_VERSION, protocolRange } from '@onemind/sdk';

export interface UpdateNeeded { sent: number; min: number; max: number }

let state: UpdateNeeded | null = null;
const listeners = new Set<() => void>();

/** Reads the range from one answer; flips the app to "Update needed" when this build is below it. */
export function noteProtocol(headers: Headers, version: number = PROTOCOL_VERSION): void {
  const range = protocolRange(headers);
  if (!range || version >= range.min || state) return;
  state = { sent: version, ...range };
  listeners.forEach((l) => l());
}

/** Wraps a fetch: declares this build's generation and watches every answer's range. */
export function withProtocol<F extends (input: string, init?: RequestInit) => Promise<Response>>(fetchFn: F, version: number = PROTOCOL_VERSION) {
  return (async (input: string, init?: RequestInit) => {
    // Keep a plain object when given one: callers and tests read init.headers as a record.
    const given = init?.headers;
    const headers = given instanceof Headers ? new Headers(given) : { [PROTOCOL_HEADER]: String(version), ...(given as Record<string, string> | undefined) };
    if (headers instanceof Headers && !headers.has(PROTOCOL_HEADER)) headers.set(PROTOCOL_HEADER, String(version));
    const res = await fetchFn(input, { ...init, headers });
    noteProtocol(res.headers, version);
    return res;
  }) as F;
}

export function useUpdateNeeded(): UpdateNeeded | null {
  return useSyncExternalStore((l) => (listeners.add(l), () => listeners.delete(l)), () => state);
}

/** Tests only: forget a previous "Update needed". */
export function resetProtocolState(): void {
  state = null;
  listeners.forEach((l) => l());
}
