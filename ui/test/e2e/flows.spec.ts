// SPDX-License-Identifier: Apache-2.0
// The two apps actually run in each engine: sign in, move through the main navigation, sign out.
import { expect, test } from '@playwright/test';
import { DASH_TOKEN, DASH_URL, FIXED_TIME, UI_URL, watchErrors } from './screens';

test('dashboard: bad token refused, demo owner signs in, navigates and signs out', async ({ page }) => {
  const errors = watchErrors(page);
  await page.clock.setFixedTime(FIXED_TIME);
  await page.goto(DASH_URL);
  // Sign-in is passkey-first (refs #440): the token field sits behind "Other ways to sign in", closed when the
  // browser supports passkeys and open when it does not.
  const more = page.locator('details.dash-signin-more');
  await expect(more).toBeVisible();
  if (!(await more.evaluate((d) => (d as HTMLDetailsElement).open))) await more.getByText('Other ways to sign in').click();
  const token = page.getByLabel('Access token');
  const signIn = page.getByRole('button', { name: 'Sign in' });

  await token.fill('not-a-demo-token');
  await signIn.click();
  await expect(page.getByRole('alert')).toHaveText('That token was not accepted by the hub.');

  await token.fill(DASH_TOKEN);
  await signIn.click();
  // Home's h1 is the greeting since the dashboard wiring (it was the brand line before).
  // The demo owner's display name is the role word "Owner", which Home never greets by (greetingName in
  // greeting.ts in the Home screen folder, #440): the heading carries no name.
  const homeHeading = /^Good (morning|afternoon|evening)$/;
  await expect(page.getByRole('heading', { level: 1, name: homeHeading })).toBeVisible();
  // The shell's jobs tray floats on Home from the first paint: its stylesheet must not arrive only with a lazily loaded
  // screen (it once did: the tray sat unstyled in the page flow and every page grew by 24 px).
  await expect(page.getByRole('complementary', { name: 'Jobs in progress' })).toHaveCSS('position', 'fixed');

  // Desktop (D-016, Atlas): the dock holds the pinned places; the launcher (the OneMind logo tile) holds every screen.
  const nav = page.getByRole('navigation', { name: 'Main' });
  for (const [link, path, heading] of [
    [/^Nodes/, '/nodes', 'Nodes'],
    [/^Market/, '/market', 'Market'],
    [/^Approvals/, '/approvals', 'Approvals'],
    [/^Home/, '/', homeHeading],
  ] as const) {
    const docked = nav.getByRole('link', { name: link });
    if ((await docked.count()) > 0) await docked.first().click();
    else {
      await nav.getByRole('button', { name: /screens and apps/ }).click();
      await page.getByRole('dialog', { name: 'Launcher' }).getByRole('link', { name: link }).click();
    }
    await expect(page).toHaveURL(new URL(path, DASH_URL).href);
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
  }

  await page.getByRole('button', { name: /^Account/ }).click();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { level: 1, name: /^Welcome to (Home )?OneMind$/ })).toBeVisible();
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
