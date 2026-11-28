// SPDX-License-Identifier: Apache-2.0
import { expect, test, type Page } from '@playwright/test';

const demo = 'http://127.0.0.1:4173/#/shell/onboarding-';
// Steps (ui/src/shell/firstRun.ts): 1 place and box, 2 address, 3 You decide, 4 owner, 5 look, 6 apps, 7 backups, 8 ready.

async function recordFrames(page: Page) {
  await page.evaluate(() => {
    const frames: number[] = [];
    const start = performance.now();
    let last: number | undefined;
    let peak = 0;
    let resolveSample!: (sample: { frames: number[]; peak: number }) => void;
    const result = new Promise<{ frames: number[]; peak: number }>((resolve) => { resolveSample = resolve; });
    const frame = (stamp: number) => {
      if (last !== undefined) frames.push(stamp - last);
      last = stamp;
      peak = Math.max(peak, document.getAnimations().length);
      if (stamp - start < 650) requestAnimationFrame(frame);
      else resolveSample({ frames, peak });
    };
    requestAnimationFrame(frame);
    Object.assign(window, { setupFrameSample: result });
  });
}

// Functional checks only: shared CI runners are too noisy for hard frame-time limits (retries are 0).
async function assertFrames(page: Page) {
  const { peak } = await page.evaluate(() =>
    (window as Window & { setupFrameSample?: Promise<{ frames: number[]; peak: number }> }).setupFrameSample!);
  expect(peak).toBeGreaterThan(0);
  expect(peak).toBeLessThanOrEqual(10);
}

for (const width of [1440, 400]) {
  test(`setup transition and map at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto(demo + '1');
    const next = page.getByRole('button', { name: 'Continue' });
    await next.focus();
    await recordFrames(page);
    await page.keyboard.press('Enter');
    // Naming the place moves on to the address step and the map draws itself in the same window.
    await expect(page.getByRole('heading', { level: 2, name: 'Where is your place?' })).toBeFocused();
    await expect(page.locator('.oms-setup-map[data-drawn] [data-map-grid]')).toHaveCount(1);
    await assertFrames(page);

    await page.goto(demo + '2');
    const map = page.locator('.oms-setup-map svg');
    const finalMap = await map.innerHTML();
    await page.getByRole('button', { name: 'Draw my map' }).focus();
    await recordFrames(page);
    await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: 'Replay' })).toBeFocused();
    await assertFrames(page);
    await page.keyboard.press('Escape');
    expect(await map.innerHTML()).toBe(finalMap);
  });
}

test('the address step moves the map offline and sends nothing anywhere', async ({ page }) => {
  const elsewhere: string[] = [];
  page.on('request', (r) => { if (new URL(r.url()).hostname !== '127.0.0.1') elsewhere.push(r.url()); });
  await page.goto(demo + '2');
  await page.getByLabel('Your address').fill('12 Orchard Lane, Springfield');
  await page.getByRole('button', { name: 'Find it on this box' }).click();
  await expect(page.getByText(/no address index yet/)).toBeVisible();
  const coords = page.getByLabel('Coordinates');
  await coords.fill('https://www.openstreetmap.org/#map=17/41.8902/12.4922');
  await coords.press('Enter');
  await expect(page.locator('.oms-setup-map figcaption')).toContainText('41.89020° N, 12.49220° E · from a map link you pasted');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading', { level: 2, name: 'Where is your place?' })).toBeVisible();
  expect(elsewhere).toEqual([]);
});
