// SPDX-License-Identifier: Apache-2.0
// i18n scaffold. English only: strings of the screens added in the wiring pass live in en.ts under
// stable keys, and `t()` looks them up. Adding a language later is one more file with the same
// keys (a test checks that every key used in the code exists in en.ts). Older screens still carry
// inline English and move over screen by screen; no translations ship yet.
import { en, type MessageKey } from './en';

export type { MessageKey };

/** Look up a message and fill `{name}` placeholders. Unknown placeholders stay visible, never blank. */
export function t(key: MessageKey, vars: Record<string, string | number> = {}): string {
  return en[key].replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}
