// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import { UI_URL } from './screens';

const packs = [
  ['Atlas Night', 'dark', 'contour'],
  ['Atlas Day', 'light', 'contour'],
  ['Night Watch', 'dark', 'ember'],
  ['Greenhouse', 'light', 'mycelium'],
  ['Harbor', 'dark', 'signal'],
  ['OneMind', 'dark', 'dawn'],
  ['OneMind Light', 'light', 'dawn'],
  ['Field', 'dark', 'ember'],
  ['Village', 'light', 'harvest'],
  ['Mono', 'dark', 'lattice'],
] as const;
// The final design's teal highlight (#1E6870 light, #5FC4CB dark).
const teal = { light: 'rgb(30, 104, 112)', dark: 'rgb(95, 196, 203)' } as const;
// Signal red #CC1F2B is the button colour in both modes and in every pack.
const signal = 'rgb(204, 31, 43)';

for (const theme of ['light', 'dark'] as const) {
  test.describe(`Atlas ${theme}`, () => {
    test.beforeEach(async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(`${UI_URL}?theme=${theme}#/appearance`);
    });

    for (const [pack, modeOnApply, wallpaperOnApply] of packs) {
      test(`${pack} paints red actions and teal selection`, async ({ page }, info) => {
        const button = page.getByRole('button', { name: `${pack} pack`, exact: true });
        await button.click();
        await expect(button).toHaveAttribute('aria-pressed', 'true');
        await expect(button).toHaveCSS('color', teal[modeOnApply]);
        const wallpaper = page.getByRole('group', { name: 'Wallpaper', exact: true });
        await expect(wallpaper.locator(`input[value="${wallpaperOnApply}"]`)).toBeChecked();

        // Applying a pack sets its own light/dark mode. Exercise the requested mode afterwards.
        const settings = page.getByRole('group', { name: 'Theme', exact: true });
        const mode = settings.getByRole('radio', { name: theme === 'light' ? 'Light' : 'Dark', exact: true });
        await mode.press('Space');
        await expect(mode).toBeChecked();
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
        const primary = page.locator('.om-cz-preview .om-btn-primary');
        // The button fades its background on theme change; wait for the final colour first.
        await expect(primary).toHaveCSS('background-color', signal);
        await expect.poll(() => primary.evaluate((el) => el.getAnimations().length)).toBe(0);
        // Capture the viewport so taking the screenshot cannot scroll the button again.
        await primary.scrollIntoViewIfNeeded();
        // WebKit on the CI runner paints in software. After the theme switch, the first frames of the glass
        // surfaces (an 18px backdrop blur over the wallpaper) take several seconds each before it is back to
        // about 16 ms a frame. Wait until two frames in a row arrive at frame rate, so the stability check below
        // measures the button and not that repaint. Bounded by the test timeout, like the click and the scroll.
        await page.evaluate(async () => {
          const frame = () => new Promise<number>((resolve) => requestAnimationFrame(resolve));
          let last = await frame();
          for (let quick = 0; quick < 2; ) {
            const now = await frame();
            quick = now - last < 50 ? quick + 1 : 0;
            last = now;
          }
        });
        let shot: { png: Buffer; box: Pick<DOMRect, 'x' | 'y' | 'width' | 'height'> } | undefined;
        await expect.poll(async () => {
          const box = await primary.evaluate(async (el) => {
            const before = el.getBoundingClientRect();
            await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
            const { x, y, width, height } = el.getBoundingClientRect();
            const centre = document.elementFromPoint(x + width / 2, y + height / 2);
            if (before.x === x && before.y === y && before.width === width && before.height === height && el.contains(centre)) {
              return { x, y, width, height };
            }
            return null;
          });
          if (!box) return false;
          const png = await page.screenshot({ scale: 'css' });
          const after = await primary.evaluate((el) => {
            const { x, y, width, height } = el.getBoundingClientRect();
            return { x, y, width, height };
          });
          if (after.x !== box.x || after.y !== box.y || after.width !== box.width || after.height !== box.height) return false;
          shot = { png, box };
          return true;
        }).toBe(true);
        const { png, box } = shot!;
        await info.attach(`${pack}-${theme}.png`, { body: png, contentType: 'image/png' });
        const pixel = await page.evaluate(async ({ base64, box }) => {
          const image = new Image();
          image.src = 'data:image/png;base64,' + base64;
          await image.decode();
          const canvas = document.createElement('canvas');
          canvas.width = image.width;
          canvas.height = image.height;
          const ctx = canvas.getContext('2d')!;
          ctx.drawImage(image, 0, 0);
          // Use the dominant colour in the centre so the label's glyphs cannot determine the result.
          const width = Math.max(1, Math.floor(box.width / 2));
          const height = Math.max(1, Math.floor(box.height / 2));
          const x = Math.floor(box.x + (box.width - width) / 2);
          const y = Math.floor(box.y + (box.height - height) / 2);
          const pixels = ctx.getImageData(x, y, width, height).data;
          const counts = new Map<string, number>();
          for (let i = 0; i < pixels.length; i += 4) {
            const colour = pixels.slice(i, i + 4).join(',');
            counts.set(colour, (counts.get(colour) ?? 0) + 1);
          }
          return [...counts].sort((a, b) => b[1] - a[1])[0]![0].split(',').map(Number);
        }, { base64: png.toString('base64'), box });
        expect(pixel).toEqual([204, 31, 43, 255]);
        await expect(page.locator('.om-cz-seg-item.om-cz-on').first()).toHaveCSS('color', teal[theme]);
      });
    }

    test('a legacy wallpaper tint preserves selection and action colours', async ({ page }, info) => {
      const pack = theme === 'light' ? 'Greenhouse' : 'Harbor';
      await page.getByRole('button', { name: `${pack} pack`, exact: true }).click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      const tint = page.getByRole('radio', { name: 'OneMind Red', exact: true });
      await tint.press('Space');
      await expect(tint).toBeChecked();
      await expect(page.locator('.om-cz-seg-item.om-cz-on').first()).toHaveCSS('color', teal[theme]);
      await expect(page.locator('.om-cz-preview .om-btn-primary')).toHaveCSS('background-color', signal);
      await info.attach(`Atlas-${theme}.png`, { body: await page.screenshot(), contentType: 'image/png' });
    });
  });
}
