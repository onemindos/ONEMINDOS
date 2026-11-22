// SPDX-License-Identifier: Apache-2.0
// Applies the signed-in person's language (or the browser's before sign-in), sets <html lang>, and
// remounts its children when the language changes so every screen re-reads its messages.
import { Fragment, useLayoutEffect, type ReactNode } from 'react';
import { localeStore } from './localeStore';
import { browserLocales, resolveLocale, setLocale, useLocale } from './index';

export function LocaleProvider({ person, children }: { person: string | null; children: ReactNode }) {
  const locale = useLocale();
  useLayoutEffect(() => {
    setLocale(person ? localeStore(person).load() : resolveLocale(browserLocales()));
  }, [person]);
  useLayoutEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return <Fragment key={locale}>{children}</Fragment>;
}
