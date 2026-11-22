// SPDX-License-Identifier: Apache-2.0
import { expect, type Page } from '@playwright/test';

/**
 * The token form sits under "Other ways to sign in", which the screen folds shut when the browser
 * can use a passkey (and leaves open when it cannot). Open it only when it is shut.
 */
export async function openTokenForm(page: Page): Promise<void> {
  const field = page.getByLabel('Access token');
  await expect(page.getByRole('heading', { name: 'Welcome to OneMind' })).toBeVisible();
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
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
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
 * desktop (D-016) the dock holds the everyday screens and Launchpad ("All screens and apps") holds
 * every screen; in the Console view the sidebar holds them all.
 */
export async function navTo(page: Page, screen: 'Home' | 'Nodes' | 'Market' | 'Approvals'): Promise<void> {
  const nav = page.getByRole('navigation', { name: 'Main' });
  const direct = nav.getByRole('link', { name: screen, exact: true });
  if ((await direct.count()) > 0) return direct.first().click();
  await nav.getByRole('button', { name: /screens and apps/ }).click();
  await page.getByRole('dialog', { name: 'Launchpad' }).getByRole('link', { name: screen, exact: true }).click();
}
