// SPDX-License-Identifier: Apache-2.0
// Known serious/critical axe findings: defects in ui/ that this suite found on its first run
// (2026-11-12, identical in Chromium and Firefox). Each has an id and a suggested fix in
// docs/testing/CI-MATRIX.md §1.4; the fix belongs to the ui/ stream.
//
// This list is a ratchet, not a waiver:
//   * any serious/critical finding that is not listed here still fails;
//   * a listed finding that no longer reproduces on a listed screen also fails, so the entry is
//     deleted in the same PR that fixes it and the list only gets shorter.
import type { Theme } from './screens';

export type Width = 'desktop' | 'phone';

export interface KnownFinding {
  id: string;
  rule: string;
  /** axe's node.target joined with a space. */
  target: string;
  screens: string[];
  widths: Width[];
  themes: Theme[];
  why: string;
}

const BOTH_THEMES: Theme[] = ['light', 'dark'];

export const KNOWN_A11Y: KnownFinding[] = [
  {
    id: 'A11Y-1',
    rule: 'button-name',
    target: '.oms-trigger',
    screens: ['ui-shell-palette', 'ui-shell-palette-search'],
    widths: ['phone'],
    themes: BOTH_THEMES,
    why: 'PaletteTrigger (ui/src/shell/CommandPalette.tsx) hides its text below the compact breakpoint (shell.css), leaving an icon-only button with no name',
  },
  {
    id: 'A11Y-2',
    rule: 'label-content-name-mismatch',
    target: '.oms-kbd-btn',
    screens: ['ui-shell-palette', 'ui-shell-palette-search'],
    widths: ['desktop'],
    themes: BOTH_THEMES,
    why: 'the palette close button shows "esc" but is named "Close" (WCAG 2.5.3 Label in Name)',
  },
  {
    id: 'A11Y-3',
    rule: 'color-contrast',
    target: '.oms-dimmed-more > .d-list > li',
    screens: ['ui-shell-states'],
    widths: ['desktop', 'phone'],
    themes: ['light'],
    why: 'StateView offline dimming (opacity 0.75 + grayscale, ui/src/shell/shell.css) drops body text below 4.5:1',
  },
  {
    id: 'A11Y-4',
    rule: 'scrollable-region-focusable',
    target: '.om-store-shots-list',
    screens: ['ui-store-app-immich'],
    widths: ['desktop', 'phone'],
    themes: BOTH_THEMES,
    why: 'the App Store screenshot strip (ui/src/store/AppDetail.tsx) scrolls sideways but cannot get keyboard focus',
  },
  {
    id: 'A11Y-5',
    rule: 'scrollable-region-focusable',
    target: 'section[aria-labelledby="sec-history"] > .om-table-wrap',
    screens: ['ui-updates'],
    widths: ['phone'],
    themes: BOTH_THEMES,
    why: 'Table (ui/src/components/Table.tsx) scrolls sideways at 375 px but its wrapper cannot get keyboard focus',
  },
];

export function knownFor(screen: string, width: Width, theme: Theme): KnownFinding[] {
  return KNOWN_A11Y.filter((k) => k.screens.includes(screen) && k.widths.includes(width) && k.themes.includes(theme));
}
