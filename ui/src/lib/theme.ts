// SPDX-License-Identifier: Apache-2.0
// Theme choice: 'system' follows prefers-color-scheme; 'light' / 'dark' force it.
// Stored per browser as a convenience only (it may be unavailable; that is fine).
export type ThemeChoice = 'system' | 'light' | 'dark';

const KEY = 'onemind.theme';

export function applyTheme(choice: ThemeChoice, root: HTMLElement = document.documentElement): void {
  if (choice === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', choice);
  try {
    window.localStorage.setItem(KEY, choice);
  } catch {
    /* storage blocked: the choice lasts for this page only */
  }
}

export function storedTheme(): ThemeChoice {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch {
    return 'system';
  }
}
