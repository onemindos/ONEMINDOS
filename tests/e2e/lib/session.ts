// SPDX-License-Identifier: Apache-2.0
import { expect, type Page } from '@playwright/test';

/** Sign in through the real sign-in screen (v0 static token; passkeys come with CORE-SEC-2). */
export async function signIn(page: Page, token: string): Promise<void> {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Welcome to OneMind' })).toBeVisible();
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

/** Go to a screen through the top navigation (other links on a page may share the word). */
export async function navTo(page: Page, screen: 'Home' | 'Nodes' | 'Market' | 'Approvals'): Promise<void> {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: screen, exact: true }).click();
}
