// SPDX-License-Identifier: Apache-2.0
/**
 * /spatial, the spatial engine (issue #814), on the real e2e hub under an emulated Quest Pro and
 * Quest 3 (IWER, lib/xr.ts). three.js and React Three Fiber (the session through three.js's
 * WebXRManager) load in a lazy chunk only after the readiness probe finds an immersive mode; a session starts only from Enter VR or
 * Enter AR. Each profile enters and leaves both modes with the empty scene and the frame-stats
 * overlay counts immersive frames. Assertions are on page state and frame counts, never on FPS.
 * By hand, the same page on a real Quest Pro is the device proof the pull request asks for.
 */
import { expect, test, type Page } from '@playwright/test';
import { hubEnv, type HubEnv } from '../lib/env';
import { signIn } from '../lib/session';
import { HEADSETS, emulateHeadset, exitFromHeadset, headsetSession, threeLoaded, watchScripts, type Headset } from '../lib/xr';

const env = hubEnv();
const E = env as HubEnv;
test.skip('missing' in env, 'missing' in env ? env.missing : '');

const MODES = [
  { mode: 'immersive-vr', button: 'Enter VR', label: 'VR', blendMode: 'opaque' },
  { mode: 'immersive-ar', button: 'Enter AR', label: 'AR', blendMode: 'alpha-blend' },
] as const;

/** Writes (a headset never approves, /spatial has no action controls) and requests that leave the hub. */
function recordTraffic(page: Page) {
  const writes: string[] = [];
  const offHub: string[] = [];
  const hub = new URL(E.url).origin;
  page.on('request', r => {
    const url = new URL(r.url());
    if (!['GET', 'HEAD', 'OPTIONS'].includes(r.method())) writes.push(`${r.method()} ${url.pathname}`);
    if (/^https?:$/.test(url.protocol) && url.origin !== hub) offHub.push(url.origin);
  });
  return { writes, offHub };
}

async function openSpatial(page: Page, headset: Headset) {
  await emulateHeadset(page, headset);
  await signIn(page, E.ownerToken);
  await page.goto('/spatial');
  await expect(page.getByRole('heading', { name: 'Spatial', exact: true })).toBeVisible();
}

const stats = (page: Page) => page.getByTestId('frame-stats');

test('without a headset /spatial says so and never downloads three.js; other pages never do', async ({ page }) => {
  const scripts = watchScripts(page);
  await signIn(page, E.ownerToken);
  await page.goto('/settings/about');
  await expect(page.getByRole('link', { name: 'Open spatial', exact: true })).toBeVisible();
  expect(await threeLoaded(scripts), 'three.js in a chunk the main pages load').toBe(false);
  await page.getByRole('link', { name: 'Open spatial', exact: true }).click();
  await expect(page).toHaveURL(/\/spatial$/);
  await expect(page.getByText(/no immersive mode|could not be checked/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Enter VR' })).toHaveCount(0);
  expect(await threeLoaded(scripts), 'three.js loaded without an immersive mode').toBe(false);
});

for (const headset of Object.keys(HEADSETS) as Headset[]) {
  const profile = HEADSETS[headset];
  test.describe(profile.name, () => {
    test('loads the engine after the probe and starts no session on its own', async ({ page }) => {
      const scripts = watchScripts(page);
      await openSpatial(page, headset);
      await expect(page.getByRole('button', { name: 'Enter VR' })).toBeEnabled();
      await expect(page.getByRole('button', { name: 'Enter AR' })).toBeEnabled();
      expect(await threeLoaded(scripts), 'the lazy engine chunk carries three.js').toBe(true);
      await expect(stats(page)).toHaveAttribute('data-mode', 'none');
      await page.waitForTimeout(2000); // a page that offered or auto-entered a session would have by now
      expect(await headsetSession(page)).toEqual({ active: false, blendMode: null });
      await expect(stats(page)).toHaveAttribute('data-frames', '0');
    });

    for (const { mode, button, label, blendMode } of MODES) {
      test(`${mode}: the button enters with the empty scene, frames are counted, the headset exits`, async ({ page }) => {
        await openSpatial(page, headset);
        const traffic = recordTraffic(page);
        const enter = page.getByRole('button', { name: button });
        await expect(enter).toBeEnabled();
        await enter.click();
        await expect(page.getByText(`${label} session running.`, { exact: false })).toBeVisible();
        expect(await headsetSession(page)).toEqual({ active: true, blendMode });
        await expect(stats(page)).toHaveAttribute('data-mode', mode);
        await expect.poll(async () => Number(await stats(page).getAttribute('data-frames')), { timeout: 60_000 }).toBeGreaterThan(30);
        await expect(stats(page)).toContainText('0 draw calls'); // the scene is empty: three.js clears, draws nothing
        await expect(page.getByRole('button', { name: button })).toBeDisabled();

        await exitFromHeadset(page);
        await expect(stats(page)).toHaveAttribute('data-mode', 'none');
        expect(await headsetSession(page)).toEqual({ active: false, blendMode: null });
        await expect(enter).toBeEnabled();
        expect(traffic.writes).toEqual([]);
        expect(traffic.offHub, 'no controller models or other assets fetched from outside the hub').toEqual([]);
      });
    }

    test('the Exit session button ends a running session', async ({ page }) => {
      await openSpatial(page, headset);
      await page.getByRole('button', { name: 'Enter VR' }).click();
      await expect(stats(page)).toHaveAttribute('data-mode', 'immersive-vr');
      // The button is for a person at the desk (a tethered headset on desktop Chrome keeps the page on
      // the monitor). IWER instead draws the headset's view over the whole page while a session runs,
      // so a pointer click at the button's position lands on the emulator's overlay. Click the button
      // element itself; the page's own handler still has to end the session.
      const exit = page.getByRole('button', { name: 'Exit session' });
      await expect(exit).toBeEnabled();
      await exit.dispatchEvent('click');
      await expect(stats(page)).toHaveAttribute('data-mode', 'none');
      expect(await headsetSession(page)).toEqual({ active: false, blendMode: null });
    });
  });
}
