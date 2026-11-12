// SPDX-License-Identifier: Apache-2.0
// Visual regression: each screen below is compared with the approved baseline for this engine in
// ui/test/visual/<browser>/. A difference above 0.1% of the pixels fails and the report shows
// expected, actual and diff. Accepting a change: ui/test/README.md "Visual baseline".
import { expect, test } from '@playwright/test';
import { DASH_SCREENS, UI_SCREENS, open, type Screen, type Theme } from './screens';

const byName = (name: string): Screen => {
  const s = [...UI_SCREENS, ...DASH_SCREENS].find((x) => x.name === name);
  if (!s) throw new Error(`unknown screen ${name}`);
  return s;
};

// Full-page shots at 1280 px: every primary screen, the component gallery and the main flows.
const DESKTOP_LIGHT = [
  'ui-home', 'ui-apps', 'ui-app-home-assistant', 'ui-approvals', 'ui-activity', 'ui-nodes', 'ui-backups',
  'ui-updates', 'ui-notifications', 'ui-settings', 'ui-gallery', 'ui-store', 'ui-system', 'ui-shell-states',
  'ui-shell-onboarding-1', 'ui-appearance',
  'dash-signin', 'dash-home', 'dash-nodes', 'dash-market', 'dash-market-uptime-kuma', 'dash-approvals',
];
const DESKTOP_DARK = ['ui-home', 'ui-approvals', 'ui-gallery'];
// Phone: one screen-height shot, so the fixed tab bar sits where a person sees it.
const PHONE = [
  { name: 'ui-home', theme: 'light' },
  { name: 'ui-approvals', theme: 'light' },
  { name: 'ui-approvals', theme: 'dark' },
  { name: 'dash-home', theme: 'light' },
] as const;

test.describe('visual', { tag: '@visual' }, () => {
  for (const name of DESKTOP_LIGHT) {
    test(`${name} light`, async ({ page }) => {
      await open(page, byName(name), 'light');
      await expect(page).toHaveScreenshot(`${name}.png`, { fullPage: true });
    });
  }
  test.describe('dark', () => {
    test.use({ colorScheme: 'dark' });
    for (const name of DESKTOP_DARK) {
      test(`${name} dark`, async ({ page }) => {
        await open(page, byName(name), 'dark');
        await expect(page).toHaveScreenshot(`${name}-dark.png`, { fullPage: true });
      });
    }
  });
  test.describe('phone', () => {
    test.use({ viewport: { width: 390, height: 844 } });
    for (const { name, theme } of PHONE) {
      test(`${name} ${theme} phone`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme });
        await open(page, byName(name), theme as Theme);
        await expect(page).toHaveScreenshot(`${name}${theme === 'dark' ? '-dark' : ''}-phone.png`);
      });
    }
  });
});
