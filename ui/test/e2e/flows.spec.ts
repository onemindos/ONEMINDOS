// SPDX-License-Identifier: Apache-2.0
// The two apps actually run in each engine: sign in, move through the main navigation, sign out.
import { expect, test } from '@playwright/test';
import { DASH_TOKEN, DASH_URL, FIXED_TIME, UI_URL, stillFrames, watchErrors } from './screens';

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
  await page.goto(`${UI_URL}?theme=light#/home`);
  await stillFrames(page);
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
