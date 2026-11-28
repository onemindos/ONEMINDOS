// SPDX-License-Identifier: Apache-2.0
import { expect, type Page } from '@playwright/test';

/** The box name the golden path saves when it finishes first-run setup (see finishFirstRun). */
const FIRST_RUN_BOX = 'home-hub';

/**
 * The token form sits under "Other ways to sign in", which the screen folds shut when the browser
 * can use a passkey (and leaves open when it cannot). Open it only when it is shut.
 */
export async function openTokenForm(page: Page): Promise<void> {
  const field = page.getByLabel('Access token');
  // The heading names the box once first-run setup saved a box name (PR #563); "OneMind" before that.
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(`^Welcome to (OneMind|${FIRST_RUN_BOX})$`) })).toBeVisible();
  if (!(await field.isVisible())) await page.getByText('Other ways to sign in', { exact: true }).click();
  await expect(field).toBeVisible();
}

/** Sign in through the real sign-in screen (v0 static token; passkeys come with CORE-SEC-2). */
export async function signIn(page: Page, token: string): Promise<void> {
  await page.goto('/');
  await openTokenForm(page);
  const field = page.getByLabel('Access token');
  await field.click();
  // Not fill()/type()/keyboard.insertText(): Playwright writes their value into the step title, which
  // lands in the HTML report CI uploads. An evaluate step's title carries no arguments. The native
  // setter plus an input event is what React's onChange listens to.
  await field.evaluate((el, value) => {
    const input = el as HTMLInputElement;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }, token);
  await page.getByRole('button', { name: 'Sign in' }).click();
  const nav = page.getByRole('navigation', { name: 'Main' });
  // The wizard's page heading (h1 "Set up OneMind") is visually hidden; each step's title is its visible
  // h2, and a fresh box opens on the first step, "Your place" (PR #1071 and the mixed first run,
  // ui/src/shell/firstRun.ts ONBOARDING_STEPS).
  const wizard = page.getByRole('heading', { level: 2, name: 'Name your place and box' });
  await expect(nav.or(wizard)).toBeVisible();
  if (await wizard.isVisible()) await finishFirstRun(page, token);
  await expect(nav).toBeVisible();
}

/**
 * A fresh box opens the first-run wizard after the owner's first sign-in (PR #551: the gateway decides,
 * GET /v1/onboarding/state). Its owner step needs a real passkey ceremony, which a headless CI browser on
 * a plain-http hub cannot do, so save the same first-run settings the wizard saves (PUT
 * /v1/onboarding/settings, the headless twin of the wizard) and reload: the shell must then open.
 */
async function finishFirstRun(page: Page, token: string): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` };
  const saved = await page.request.put('/v1/onboarding/settings', {
    headers,
    data: { box_name: FIRST_RUN_BOX, time_zone: 'UTC', backup_choice: 'later', backup_destination_id: null },
  });
  expect(saved.status(), 'PUT /v1/onboarding/settings').toBe(200);
  const state = await page.request.get('/v1/onboarding/state', { headers });
  expect(state.status(), 'GET /v1/onboarding/state').toBe(200);
  expect((await state.json()).complete, 'first-run setup complete after saving its settings').toBe(true);
  await page.reload();
}

/**
 * Press Approve on the Approvals card titled `title` (e.g. "Install ntfy") and wait for the hub's
 * answer. The gateway runs the change before it answers, so this can take minutes.
 */
export async function approveOnScreen(page: Page, title: string, timeout: number): Promise<string> {
  await page.getByRole('button', { name: `Approve ${title}` }).click();
  const status = page.getByRole('status').filter({ hasText: `${title}:` });
  await expect(status).toBeVisible({ timeout });
  return (await status.textContent())?.trim() ?? '';
}

/**
 * Go to a screen through the main navigation (other links on a page may share the word). On the
 * desktop (D-016) the dock holds the everyday screens and the launcher dialog ("Launcher", opened from
 * the logo tile "launcher: all screens and apps", #1341) holds every screen; in the Console view the
 * sidebar holds them all.
 */
export async function navTo(page: Page, screen: 'Home' | 'Nodes' | 'Market' | 'Approvals'): Promise<void> {
  const nav = page.getByRole('navigation', { name: 'Main' });
  const direct = nav.getByRole('link', { name: screen, exact: true });
  if ((await direct.count()) > 0) return direct.first().click();
  await nav.getByRole('button', { name: /screens and apps/ }).click();
  // A launcher tile's name is the screen name plus its badge when work waits there ("Approvals 1 waiting").
  const tile = new RegExp(`^${screen}(?: \\d+ waiting)?$`);
  await page.getByRole('dialog', { name: 'Launcher' }).getByRole('link', { name: tile }).click();
}
