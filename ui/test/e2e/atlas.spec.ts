// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import { UI_URL } from './screens';

for (const theme of ['light', 'dark'] as const) {
  test.describe(`Atlas ${theme}`, () => {
    const selection = theme === 'light' ? 'rgb(31, 106, 102)' : 'rgb(109, 184, 176)';
    test.beforeEach(async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(`${UI_URL}?theme=${theme}#/appearance`);
      const settings = page.getByRole('group', { name: 'Theme', exact: true });
      const mode = settings.getByRole('radio', { name: theme === 'light' ? 'Light' : 'Dark', exact: true });
      await mode.press('Space');
      await expect(mode).toBeChecked();
    });

    for (const pack of ['Contour', 'Paper', 'Fjord']) {
      test(`${pack} paints red actions and teal selection`, async ({ page }, info) => {
        await page.getByRole('button', { name: `${pack} pack` }).click();
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
        const active = page.getByRole('button', { name: `${pack} pack`, pressed: true });
        await expect(active).toHaveCSS('color', selection);
      });
    }

    test('a legacy wallpaper tint preserves selection and action colours', async ({ page }, info) => {
      await page.getByRole('button', { name: 'Fjord pack' }).click();
      const tint = page.getByRole('radio', { name: 'OneMind Red', exact: true });
      await tint.press('Space');
      await expect(tint).toBeChecked();
      await expect(page.locator('.om-cz-seg-item.om-cz-on').first()).toHaveCSS('color', selection);
      await expect(page.locator('.om-cz-preview .om-btn-primary')).toHaveCSS('background-color', theme === 'light' ? 'rgb(209, 24, 38)' : 'rgb(251, 96, 90)');
      await info.attach(`Atlas-${theme}.png`, { body: await page.screenshot(), contentType: 'image/png' });
    });
  });
}
