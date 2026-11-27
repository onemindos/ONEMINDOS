// SPDX-License-Identifier: Apache-2.0
/**
 * /spatial/diagnostics on the real e2e hub under an emulated Quest Pro and Quest 3 (issue #813).
 * The dashboard is the one the hub serves; the headset is IWER (lib/xr.ts), installed before the
 * page loads. Each profile enters and leaves immersive-vr and immersive-ar twice: once letting the
 * three marker loads finish, once exiting from the headset in the middle while scripted controllers
 * and hands press. Assertions are on page state, the device report and draw counts, never on FPS
 * (the emulator proves behaviour, not speed). By hand, the same screen on a real Quest Pro is the
 * #803 kit, whose JSON report belongs on the pull request.
 */
import { expect, test, type Page } from '@playwright/test';
import { hubEnv, type HubEnv } from '../lib/env';
import { signIn } from '../lib/session';
import { HEADSETS, emulateHeadset, exitFromHeadset, headsetSession, rendererInfo, scriptControllersAndHands, type Headset } from '../lib/xr';

const env = hubEnv();
const E = env as HubEnv;
test.skip('missing' in env, 'missing' in env ? env.missing : '');

const MODES = [
  { mode: 'immersive-vr', button: 'Start VR test', blendMode: 'opaque' },
  { mode: 'immersive-ar', button: 'Start AR test', blendMode: 'alpha-blend' },
] as const;

/** A headset never approves and /spatial has no action controls: the page must not write anything. */
function recordWrites(page: Page): string[] {
  const writes: string[] = [];
  page.on('request', r => { if (!['GET', 'HEAD', 'OPTIONS'].includes(r.method())) writes.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  return writes;
}

async function report(page: Page) {
  return JSON.parse((await page.getByTestId('spatial-report').textContent()) ?? '{}');
}

async function openDiagnostics(page: Page, headset: Headset) {
  await emulateHeadset(page, headset);
  await signIn(page, E.ownerToken);
  await page.goto('/spatial/diagnostics');
  await expect(page.getByRole('heading', { name: 'Spatial diagnostics' })).toBeVisible();
}

for (const headset of Object.keys(HEADSETS) as Headset[]) {
  const profile = HEADSETS[headset];
  test.describe(profile.name, () => {
    test('Settings › About reports VR and AR ready and links to the diagnostics', async ({ page }) => {
      await emulateHeadset(page, headset);
      await signIn(page, E.ownerToken);
      await page.goto('/settings/about');
      await expect(page.getByText('Ready for VR and AR', { exact: true })).toBeVisible();
      await page.getByRole('link', { name: 'Spatial diagnostics', exact: true }).click();
      await expect(page).toHaveURL(/\/spatial\/diagnostics$/);
      await expect(page.getByRole('button', { name: 'Start VR test' })).toBeEnabled();
      await expect(page.getByRole('button', { name: 'Start AR test' })).toBeEnabled();
    });

    for (const { mode, button, blendMode } of MODES) {
      test(`${mode}: enters, renders the 100, 500 and 2,000 marker loads, exits`, async ({ page }) => {
        await openDiagnostics(page, headset);
        const writes = recordWrites(page);
        const start = page.getByRole('button', { name: button });
        await expect(start).toBeEnabled();
        await start.click();
        await expect(page.getByText('Session running.', { exact: true })).toBeVisible();
        expect(await headsetSession(page)).toEqual({ active: true, blendMode });
        await expect(page.getByText('Session completed.', { exact: true })).toBeVisible({ timeout: 300_000 }); // software WebGL on a CI runner
        expect(await headsetSession(page), 'the page ended the session').toEqual({ active: false, blendMode: null });

        const r = await report(page);
        expect(r.browser).toContain(profile.userAgent);
        expect(r.readiness).toMatchObject({ secure: true, vr: 'available', ar: 'available' });
        expect(r.session).toMatchObject({ mode, status: 'completed', startedAt: expect.any(String) });
        expect(r.session.frameRates.map((s: { assets: number }) => s.assets)).toEqual([100, 500, 2000]);
        // Draws, not speed: every load was drawn as one batch of points, at least once per measured frame.
        const info = await rendererInfo(page);
        expect([...info.pointBatches].sort((a, b) => a - b)).toEqual([100, 500, 2000]);
        expect(info.calls).toBeGreaterThanOrEqual(3 * 90);
        expect(info.points).toBeGreaterThanOrEqual(90 * (100 + 500 + 2000));
        expect(writes).toEqual([]);
        // The buttons come back for another run.
        await expect(start).toBeEnabled();
      });

      test(`${mode}: scripted controllers and hands change nothing, the headset exits mid-run`, async ({ page }) => {
        await openDiagnostics(page, headset);
        const writes = recordWrites(page);
        await page.getByRole('button', { name: button }).click();
        await expect(page.getByText('Session running.', { exact: true })).toBeVisible();

        const input = await scriptControllersAndHands(page);
        expect(input.controllers.map(s => s.handedness).sort()).toEqual(['left', 'right']);
        for (const s of input.controllers) expect(s.profiles).toContain(profile.controllerProfile);
        // The screen does not ask for 'hand-tracking', so it gets no hand joints; the pinch still selects.
        expect(input.hands.filter(s => s.hand)).toEqual([]);
        expect(input.selects).toEqual(['controller-right', 'hand-left']);
        await expect(page.getByText('Session running.', { exact: true })).toBeVisible();

        await exitFromHeadset(page);
        await expect(page.getByText('Session interrupted.', { exact: true })).toBeVisible();
        expect(await headsetSession(page)).toEqual({ active: false, blendMode: null });
        const r = await report(page);
        expect(r.session).toMatchObject({ mode, status: 'interrupted' });
        expect(r.session.frameRates.length).toBeLessThan(3);
        expect((await rendererInfo(page)).calls).toBeGreaterThan(0);
        expect(writes).toEqual([]);
      });
    }
  });
}
