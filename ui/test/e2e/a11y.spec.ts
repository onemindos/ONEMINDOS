// SPDX-License-Identifier: Apache-2.0
// axe-core on every screen (e2e/screens.ts) in light and dark, at desktop and phone width, in each
// engine; any serious or critical finding fails unless it is a listed known finding
// (e2e/known-a11y.ts, which must still reproduce). The same visit fails on an uncaught exception
// or a console error. Register rows TR-181 (contrast and a11y in a real browser) and TR-183 (engines).
import { test } from '@playwright/test';
import { knownFor, type Width } from './known-a11y';
import { DASH_SCREENS, UI_SCREENS, expectNoSeriousAxeViolations, open, watchErrors, type Screen, type Theme } from './screens';

const WIDTHS: Array<{ name: Width; viewport: { width: number; height: number } }> = [
  { name: 'desktop', viewport: { width: 1280, height: 860 } },
  { name: 'phone', viewport: { width: 375, height: 812 } },
];

function check(s: Screen, theme: Theme, width: Width) {
  test(`${s.name} ${theme}`, async ({ page }, testInfo) => {
    const errors = watchErrors(page);
    await open(page, s, theme);
    await expectNoSeriousAxeViolations(page, testInfo, knownFor(s.name, width, theme));
    test.expect(errors, 'uncaught exceptions or console errors').toEqual([]);
  });
}

for (const w of WIDTHS) {
  test.describe(`a11y ${w.name}`, () => {
    test.use({ viewport: w.viewport });
    for (const theme of ['light', 'dark'] as const) {
      test.describe(theme, () => {
        test.use({ colorScheme: theme });
        for (const s of UI_SCREENS) check(s, theme, w.name);
      });
    }
    // The dashboard has no dark theme yet (dashboard/src/styles.css); it is checked in light.
    for (const s of DASH_SCREENS) check(s, 'light', w.name);
  });
}
