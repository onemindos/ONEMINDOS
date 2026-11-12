// SPDX-License-Identifier: Apache-2.0
// axe-core on every screen (e2e/screens.ts) in light and dark, at desktop and phone width, in each
// engine; any serious or critical finding fails. The same visit fails on an uncaught exception or a
// console error. Register rows TR-181 (contrast and a11y in a real browser) and TR-183 (engines).
import { test } from '@playwright/test';
import { DASH_SCREENS, UI_SCREENS, expectNoSeriousAxeViolations, open, watchErrors, type Screen, type Theme } from './screens';

const WIDTHS = [
  { name: 'desktop', viewport: { width: 1280, height: 860 } },
  { name: 'phone', viewport: { width: 375, height: 812 } },
] as const;

function check(s: Screen, theme: Theme) {
  test(`${s.name} ${theme}`, async ({ page }, testInfo) => {
    const errors = watchErrors(page);
    await open(page, s, theme);
    await expectNoSeriousAxeViolations(page, testInfo);
    test.expect(errors, 'uncaught exceptions or console errors').toEqual([]);
  });
}

for (const w of WIDTHS) {
  test.describe(`a11y ${w.name}`, () => {
    test.use({ viewport: w.viewport });
    for (const theme of ['light', 'dark'] as const) {
      test.describe(theme, () => {
        test.use({ colorScheme: theme });
        for (const s of UI_SCREENS) check(s, theme);
      });
    }
    // The dashboard has no dark theme yet (dashboard/src/styles.css); it is checked in light.
    for (const s of DASH_SCREENS) check(s, 'light');
  });
}
