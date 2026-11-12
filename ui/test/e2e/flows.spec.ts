// SPDX-License-Identifier: Apache-2.0
// The two apps actually run in each engine: sign in, move through the main navigation, sign out.
import { expect, test } from '@playwright/test';
import { DASH_TOKEN, DASH_URL, FIXED_TIME, UI_URL, watchErrors } from './screens';

test('dashboard: bad token refused, demo owner signs in, navigates and signs out', async ({ page }) => {
  const errors = watchErrors(page);
  await page.clock.setFixedTime(FIXED_TIME);
  await page.goto(DASH_URL);
  const token = page.getByLabel('Access token');
  const signIn = page.getByRole('button', { name: 'Sign in' });

  await token.fill('not-a-demo-token');
  await signIn.click();
  await expect(page.getByRole('alert')).toHaveText('That token was not accepted by the hub.');

  await token.fill(DASH_TOKEN);
  await signIn.click();
  await expect(page.getByRole('heading', { level: 1, name: 'Home OneMind' })).toBeVisible();

  const nav = page.getByRole('navigation', { name: 'Main' });
  for (const [link, path, heading] of [
    [/^Nodes/, '/nodes', 'Machines'],
    [/^Market/, '/market', 'Market'],
    [/^Approvals/, '/approvals', 'Approvals'],
    [/^Home/, '/', 'Home OneMind'],
  ] as const) {
    await nav.getByRole('link', { name: link }).click();
    await expect(page).toHaveURL(new URL(path, DASH_URL).href);
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
  }

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Welcome to OneMind' })).toBeVisible();
  expect(errors, 'uncaught exceptions or console errors').toEqual([]);
});

test('ui demo: every main navigation entry opens its screen', async ({ page }) => {
  const errors = watchErrors(page);
  await page.clock.setFixedTime(FIXED_TIME);
  // Starts on Activity and ends on Home without clicking there: WebKit cannot interact on Home (WK-1, below).
  await page.goto(`${UI_URL}?theme=light#/activity`);
  const nav = page.getByRole('navigation', { name: 'Main', exact: true });
  await expect(nav).toBeVisible();
  // ui/demo/src/DemoApp.tsx NAV
  for (const [label, id] of [
    ['Apps', 'apps'],
    ['Approvals', 'approvals'],
    ['Activity', 'activity'],
    ['Alerts', 'notifications'],
    ['Nodes', 'nodes'],
    ['Backups', 'backups'],
    ['Updates', 'updates'],
    ['Settings', 'settings'],
    ['Components', 'gallery'],
    ['Home', 'home'],
  ] as const) {
    await nav.getByRole('link', { name: new RegExp(`^${label}`) }).click();
    await expect(page).toHaveURL(new RegExp(`#/${id}$`));
    await expect(nav.getByRole('link', { name: new RegExp(`^${label}`) })).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('#om-main h1').first()).toBeVisible();
  }
  expect(errors, 'uncaught exceptions or console errors').toEqual([]);
});

// WK-1 (docs/testing/CI-MATRIX.md §1.5): in WebKit on the Linux runner, Home stops producing frames,
// so a click there never passes Playwright's actionability check. Expected to fail in WebKit only.
// When it starts passing there, Playwright reports "expected to fail, but passed": delete the
// test.fail line and the WK-1 skips in visual.spec.ts.
test('WK-1 ratchet: a click on Home works', async ({ page, browserName }) => {
  test.fail(browserName === 'webkit', 'WK-1: WebKit stops producing frames on Home');
  await page.clock.setFixedTime(FIXED_TIME);
  await page.goto(`${UI_URL}?theme=light#/home`);
  const nav = page.getByRole('navigation', { name: 'Main', exact: true });
  await nav.getByRole('link', { name: /^Apps/ }).click({ timeout: 15_000 });
  await expect(page).toHaveURL(/#\/apps$/);
});
