// SPDX-License-Identifier: Apache-2.0
/** Join class names, skipping falsy ones. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
