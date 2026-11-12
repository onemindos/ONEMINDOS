// SPDX-License-Identifier: Apache-2.0
// Visual regression: each screen below is compared with the approved baseline for this engine in
// ui/test/visual/<browser>/. A difference above 0.1% of the pixels fails and the report shows
// expected, actual and diff. Accepting a change: ui/test/README.md "Visual baseline".
import { expect, test, type Page } from '@playwright/test';
import { DASH_SCREENS, UI_SCREENS, open, settle, type Screen, type Theme } from './screens';

const byName = (name: string): Screen => {
  const s = [...UI_SCREENS, ...DASH_SCREENS].find((x) => x.name === name);
  if (!s) throw new Error(`unknown screen ${name}`);
  return s;
};

/**
 * The whole page at 1280 px. The viewport is stretched to the page's height instead of using a
 * full-page capture: a full-page capture draws position: fixed layers (wallpaper, Home dock, page
 * background) only within the first screen, which puts the dock in the middle of the picture.
 */
async function wholePage(page: Page, file: string) {
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width: 1280, height: Math.min(Math.max(height, 860), 8000) });
  await settle(page);
  await expect(page).toHaveScreenshot(file);
}

// Whole pages at 1280 px: every primary screen, the component gallery and the main flows.
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
      await wholePage(page, `${name}.png`);
    });
  }
  test.describe('dark', () => {
    test.use({ colorScheme: 'dark' });
    for (const name of DESKTOP_DARK) {
      test(`${name} dark`, async ({ page }) => {
        await open(page, byName(name), 'dark');
        await wholePage(page, `${name}-dark.png`);
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
