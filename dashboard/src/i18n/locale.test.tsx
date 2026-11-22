// SPDX-License-Identifier: Apache-2.0
// UMB-P13 (#431): the language mechanism. A test-only language proves it end to end; no real
// translation ships yet.
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { renderApp } from '../test/helpers';
import { availableLocales, formatDate, formatNumber, getLocale, registerLocale, resolveLocale, setLocale, t, unregisterLocale } from './index';
import { localeStore } from './localeStore';

const T = { timeout: 4000 };
const memory = (): Storage => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k), clear: () => m.clear(), key: () => null, length: 0 } as Storage;
};

afterEach(() => {
  unregisterLocale('de');
  setLocale('en');
});

describe('language catalogues', () => {
  it('English is the only language until one is registered', () => {
    expect(availableLocales()).toEqual([{ id: 'en', label: 'English' }]);
    expect(() => registerLocale('en', 'English', {})).toThrow();
  });

  it('falls back to English per key and formats with the chosen locale', () => {
    registerLocale('de', 'Deutsch', { 'common.save': 'Speichern' });
    setLocale('de');
    expect(t('common.save')).toBe('Speichern');
    expect(t('common.cancel')).toBe('Cancel'); // not translated yet: English, never blank
    expect(formatNumber(1234567.5)).toBe('1.234.567,5');
    expect(formatDate('2026-11-10T12:00:00Z', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' })).toBe('10.11.2026');
    setLocale('en');
    expect(formatNumber(1234567.5)).toBe('1,234,567.5');
  });

  it('resolves the browser language to a supported one', () => {
    registerLocale('de', 'Deutsch', {});
    expect(resolveLocale(['fr-FR', 'de-AT'])).toBe('de');
    expect(resolveLocale('xx')).toBe('en');
    expect(resolveLocale(null)).toBe('en');
  });

  it('remembers the choice per person', () => {
    registerLocale('de', 'Deutsch', {});
    const base = memory();
    localeStore('owner', base).save('de');
    expect(localeStore('owner', base).load()).toBe('de');
    expect(localeStore('alex', base).load()).toBe('en');
    expect(localeStore('owner', null).load()).toBe('en'); // no storage: default
  });
});

describe('Settings language picker', () => {
  it('switches every screen and the page language, and keeps the choice for the person', async () => {
    registerLocale('de', 'Deutsch', { 'language.title': 'Sprache', 'language.label': 'Oberflächensprache', 'account.title': 'Konto und Sicherheit' });
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings' });
    const select = await screen.findByLabelText('Interface language', {}, T);
    await u.selectOptions(select, 'de');
    expect(await screen.findByLabelText('Oberflächensprache', {}, T)).toHaveValue('de');
    expect(document.documentElement.lang).toBe('de');
    expect(getLocale()).toBe('de');
    // another screen follows
    await u.click(await screen.findByRole('link', { name: /Account/ }, T));
    expect(await screen.findByRole('heading', { name: 'Konto und Sicherheit' }, T)).toBeInTheDocument();
    await waitFor(() => expect([...Object.keys(window.localStorage ?? {})].some((k) => k.endsWith(':ui.locale'))).toBe(true));
  });
});
