// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import { UI_URL } from './screens';

const packs = [
  ['Atlas Night', 'dark', 'contour'],
  ['Atlas Day', 'light', 'contour'],
  ['Night Watch', 'dark', 'dusk'],
  ['Greenhouse', 'light', 'meadow'],
  ['Harbor', 'dark', 'tide'],
  ['Console Default', 'dark', 'onemind'],
  ['Console Light', 'light', 'aurora'],
  ['Field', 'dark', 'signal'],
  ['Village', 'light', 'dunes'],
  ['Mono', 'dark', 'none'],
] as const;
const teal = { light: 'rgb(31, 106, 102)', dark: 'rgb(109, 184, 176)' } as const;

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
        // Read the painted pixels, including the effects of stylesheet order and theme overrides.
        const png = await primary.screenshot();
        await info.attach(`${pack}-${theme}.png`, { body: png, contentType: 'image/png' });
        const pixel = await page.evaluate(async (base64) => {
          const image = new Image();
          image.src = 'data:image/png;base64,' + base64;
          await image.decode();
          const ctx = document.createElement('canvas').getContext('2d')!;
          ctx.drawImage(image, 0, 0);
          return Array.from(ctx.getImageData(7, Math.floor(image.height / 2), 1, 1).data);
        }, png.toString('base64'));
        expect(pixel).toEqual(theme === 'light' ? [209, 24, 38, 255] : [251, 96, 90, 255]);
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
      await expect(page.locator('.om-cz-preview .om-btn-primary')).toHaveCSS('background-color', theme === 'light' ? 'rgb(209, 24, 38)' : 'rgb(251, 96, 90)');
      await info.attach(`Atlas-${theme}.png`, { body: await page.screenshot(), contentType: 'image/png' });
    });
  });
}
