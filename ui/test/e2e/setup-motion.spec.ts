// SPDX-License-Identifier: Apache-2.0
import { expect, test, type Page } from '@playwright/test';

const demo = 'http://127.0.0.1:4173/#/shell/onboarding-';

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

async function assertFrames(page: Page) {
  const { frames, peak } = await page.evaluate(() =>
    (window as Window & { setupFrameSample?: Promise<{ frames: number[]; peak: number }> }).setupFrameSample!);
  frames.sort((a, b) => a - b);
  expect(frames.length).toBeGreaterThanOrEqual(20);
  expect(peak).toBeGreaterThan(0);
  expect(peak).toBeLessThanOrEqual(10);
  expect(frames.at(-1)!).toBeLessThanOrEqual(50);
  expect(frames[Math.ceil(frames.length * 0.95) - 1]!).toBeLessThanOrEqual(20);
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
    await expect(page.getByRole('heading', { level: 2, name: 'Create the owner' })).toBeFocused();
    await assertFrames(page);

    await page.goto(demo + '6');
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
