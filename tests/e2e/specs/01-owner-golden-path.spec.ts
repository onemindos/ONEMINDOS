// SPDX-License-Identifier: Apache-2.0
/**
 * Golden path, owner side (contract §3, §5, §10.3): sign in, see the node, open the Market,
 * request an install, approve it, see it succeed, remove it again. All through the dashboard;
 * REST is only used to cross-check what the screen says.
 */
import { expect, test } from '@playwright/test';
import { APPROVE_TIMEOUT_MS, hubEnv, type HubEnv } from '../lib/env';
import { Hub } from '../lib/hub';
import { approveOnScreen, signIn } from '../lib/session';

test.describe.configure({ mode: 'serial' });

const env = hubEnv();
const E = env as HubEnv;
test.skip('missing' in env, 'missing' in env ? env.missing : '');

test.beforeAll(async ({ request }) => {
  // A previous, interrupted run may have left the app installed: start from "not installed".
  const hub = new Hub(request, E.url, E.ownerToken);
  if ((await hub.app(E.app)).installed) await hub.requestAndApprove('app.remove', E.app, APPROVE_TIMEOUT_MS);
});

test('a wrong token is refused on the sign-in screen', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Access token').fill('not-a-real-token-0000000000000000');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toHaveText('That token was not accepted by the hub.');
});

test('the owner signs in and sees the hub node online', async ({ page, request }) => {
  const hub = new Hub(request, E.url, E.ownerToken);
  // onemindd heartbeats every few seconds; allow the first one to arrive after install.
  await expect
    .poll(async () => (await hub.nodes()).filter((n) => n.role === 'hub' && n.status === 'online').length, {
      timeout: 120_000,
    })
    .toBeGreaterThan(0);
  const node = (await hub.nodes()).find((n) => n.role === 'hub' && n.status === 'online')!;

  await signIn(page, E.ownerToken);
  await page.getByRole('link', { name: 'Nodes' }).click();
  const card = page.getByRole('article', { name: node.hostname });
  await expect(card).toBeVisible();
  await expect(card).toContainText('Hub');
  await expect(card).toContainText('Online');
});

test('the Market lists the app with its trust facts, and blocks an unscanned one', async ({ page, request }) => {
  const hub = new Hub(request, E.url, E.ownerToken);
  const app = await hub.app(E.app);
  expect(app.scan?.result, `${E.app} needs a passing scan record (the harness provides it)`).toBe('pass');

  await signIn(page, E.ownerToken);
  await page.getByRole('link', { name: 'Market' }).click();
  const card = page.getByRole('article', { name: app.name });
  await expect(card).toContainText('Licence');
  await expect(card).toContainText('passed');
  await expect(card.getByRole('button', { name: `Install ${app.name}` })).toBeEnabled();

  const blocked = (await hub.apps()).find((a) => a.id === E.unscannedApp);
  test.skip(!blocked || !!blocked.scan, `${E.unscannedApp} is not in the catalog unscanned on this hub`);
  const bcard = page.getByRole('article', { name: blocked!.name });
  await expect(bcard.getByRole('button', { name: `Install ${blocked!.name}` })).toBeDisabled();
  await expect(bcard).toContainText('Not scanned yet');
});

test('the owner requests the install, approves it and sees it succeed', async ({ page, request }) => {
  const hub = new Hub(request, E.url, E.ownerToken);
  const app = await hub.app(E.app);

  await signIn(page, E.ownerToken);
  await page.goto(`/market/${E.app}`);
  await page.getByRole('button', { name: `Install ${app.name}` }).click();
  await expect(page).toHaveURL(/\/approvals\?highlight=/);
  const actionId = new URL(page.url()).searchParams.get('highlight')!;

  const card = page.getByRole('article', { name: `Install ${E.app}` }).filter({ hasText: 'awaiting approval' });
  await expect(card).toContainText('Person');
  await expect(card).toContainText(`"app_id": "${E.app}"`);
  expect(await approveOnScreen(page, `Install ${E.app}`, APPROVE_TIMEOUT_MS)).toBe(`Install ${E.app}: succeeded.`);

  const done = await hub.get<{ state: string }>(`/v1/actions/${actionId}`);
  expect(done.state).toBe('succeeded');
  expect((await hub.app(E.app)).installed).toBe(true);

  await page.getByRole('link', { name: 'Market' }).click();
  const mcard = page.getByRole('article', { name: app.name });
  await expect(mcard).toContainText('Installed');
  await expect(mcard.getByRole('button', { name: `Remove ${app.name}` })).toBeEnabled();
});

test('the owner removes the app again', async ({ page, request }) => {
  const hub = new Hub(request, E.url, E.ownerToken);
  const app = await hub.app(E.app);
  expect(app.installed).toBe(true);

  await signIn(page, E.ownerToken);
  await page.getByRole('link', { name: 'Market' }).click();
  await page.getByRole('article', { name: app.name }).getByRole('button', { name: `Remove ${app.name}` }).click();
  await expect(page).toHaveURL(/\/approvals\?highlight=/);
  expect(await approveOnScreen(page, `Remove ${E.app}`, APPROVE_TIMEOUT_MS)).toBe(`Remove ${E.app}: succeeded.`);
  expect((await hub.app(E.app)).installed).toBe(false);

  await page.getByRole('link', { name: 'Market' }).click();
  await expect(page.getByRole('article', { name: app.name }).getByRole('button', { name: `Install ${app.name}` })).toBeEnabled();
});
