// SPDX-License-Identifier: Apache-2.0
// i18n plumbing (UMB-P13, issue #431). English (en.ts) is the complete source catalogue. Another
// language is one `registerLocale()` call with a partial catalogue under the same keys: a key a
// translator has not done yet shows the English text, never a blank or a raw key. The chosen
// language is kept per person (localeStore.ts) and the picker is in Settings > Appearance.
// No translation ships yet; the founder picks the first language (#431), which is a data-only PR.
import { useSyncExternalStore } from 'react';
import { en, type MessageKey } from './en';

export type { MessageKey };

export type Catalogue = Partial<Record<MessageKey, string>>;
export interface LocaleInfo {
  /** BCP 47 tag, also the Intl locale: "en", "de", "pt-BR". */
  id: string;
  /** The language's own name, shown in the picker: "Deutsch". */
  label: string;
}

export const DEFAULT_LOCALE = 'en';
const catalogues = new Map<string, Catalogue>([[DEFAULT_LOCALE, en]]);
const labels = new Map<string, string>([[DEFAULT_LOCALE, 'English']]);
let current = DEFAULT_LOCALE;
const listeners = new Set<() => void>();

/** Add (or replace) a language. English cannot be replaced. */
export function registerLocale(id: string, label: string, messages: Catalogue): void {
  if (id === DEFAULT_LOCALE) throw new Error('English is the source catalogue and cannot be replaced');
  catalogues.set(id, messages);
  labels.set(id, label);
  emit();
}

/** Remove a registered language (tests). */
export function unregisterLocale(id: string): void {
  if (id === DEFAULT_LOCALE) return;
  catalogues.delete(id);
  labels.delete(id);
  if (current === id) current = DEFAULT_LOCALE;
  emit();
}

export function availableLocales(): LocaleInfo[] {
  return [...catalogues.keys()].map((id) => ({ id, label: labels.get(id) ?? id }));
}

/**
 * Pick a supported language from a stored value or the browser's list: an exact tag first, then
 * the same base language ("de-AT" gets "de"), else English.
 */
export function resolveLocale(wanted: string | null | undefined | readonly string[]): string {
  const list = typeof wanted === 'string' ? [wanted] : (wanted ?? []);
  const ids = [...catalogues.keys()];
  for (const raw of list) {
    const tag = raw.toLowerCase();
    const exact = ids.find((i) => i.toLowerCase() === tag);
    if (exact) return exact;
    const base = tag.split('-')[0]!;
    const near = ids.find((i) => i.toLowerCase() === base) ?? ids.find((i) => i.toLowerCase().split('-')[0] === base);
    if (near) return near;
  }
  return DEFAULT_LOCALE;
}

export function browserLocales(): string[] {
  try {
    return [...(navigator.languages?.length ? navigator.languages : [navigator.language])].filter(Boolean);
  } catch {
    return [];
  }
}

function emit() {
  listeners.forEach((l) => l());
}

export function getLocale(): string {
  return current;
}

export function setLocale(id: string): void {
  const next = resolveLocale(id);
  if (next === current) return;
  current = next;
  emit();
}

export function useLocale(): string {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => void listeners.delete(cb);
    },
    getLocale,
    getLocale,
  );
}

/** Look up a message in the current language (English when missing) and fill `{name}` placeholders. Unknown placeholders stay visible, never blank. */
export function t(key: MessageKey, vars: Record<string, string | number> = {}): string {
  const text = catalogues.get(current)?.[key] ?? en[key];
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** Dates, numbers and units follow the chosen language, not the browser's. */
export function formatDate(d: Date | number | string, opts: Intl.DateTimeFormatOptions = {}): string {
  const date = d instanceof Date ? d : new Date(d);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(current, opts).format(date);
}
export function formatNumber(n: number, opts: Intl.NumberFormatOptions = {}): string {
  return new Intl.NumberFormat(current, opts).format(n);
}
