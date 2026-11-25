// SPDX-License-Identifier: Apache-2.0
// The client protocol policy (sdk/contracts/protocol-versions.md, issue 697).

/** The protocol generation this SDK speaks (sdk/contracts/protocol-versions.md). Sent on every
 *  request; the hub serves N and N-1 and refuses older with `upgrade_required`. */
export const PROTOCOL_VERSION = 2;
export const PROTOCOL_HEADER = "X-OneMind-Protocol";
export const PROTOCOL_MIN_HEADER = "X-OneMind-Protocol-Min";
export const PROTOCOL_MAX_HEADER = "X-OneMind-Protocol-Max";

/** The generations a hub serves, read from any answer's headers; undefined if the hub predates them. */
export function protocolRange(headers: Headers): { min: number; max: number } | undefined {
  const min = Number(headers.get(PROTOCOL_MIN_HEADER));
  const max = Number(headers.get(PROTOCOL_MAX_HEADER));
  return Number.isInteger(min) && Number.isInteger(max) && min > 0 && max >= min ? { min, max } : undefined;
}

/** True when a hub's answer says a client speaking `version` is too old for it. */
export function needsUpdate(headers: Headers, version: number = PROTOCOL_VERSION): boolean {
  const range = protocolRange(headers);
  return range !== undefined && version < range.min;
}
