// SPDX-License-Identifier: Apache-2.0
// The language is remembered per person, like the layout choice (shell/layoutMode.ts): in the
// person's slot of this browser, until the hub keeps preferences (data/prefs.ts). No stored choice
// means the browser's language (resolveLocale falls back to English).
import { personStorage } from '../data/prefs';
import { browserLocales, resolveLocale } from './index';

const KEY = 'ui.locale';

export function localeStore(personId: string, base?: Storage | null) {
  const s = base === undefined ? personStorage(personId) : personStorage(personId, base);
  return {
    /** The person's saved language, else the browser's, else English. */
    load(): string {
      let saved: string | null = null;
      try {
        saved = s?.getItem(KEY) ?? null; // private windows can throw on storage access
      } catch {
        saved = null;
      }
      return resolveLocale(saved ? [saved] : browserLocales());
    },
    save(id: string): void {
      try {
        s?.setItem(KEY, id);
      } catch {
        // not saved; the choice still applies until reload
      }
    },
  };
}
