// SPDX-License-Identifier: Apache-2.0
// Design-review screenshots of the dashboard mock build (dashboard/dist from `npm run build:mock`).
//   node design-shots.mjs <out dir> [dist dir]
// Desktop 1440x900 and phone 390x844, light and dark. Not part of CI.
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const out = resolve(process.argv[2] ?? 'shots');
const dist = resolve(process.argv[3] ?? '../../dashboard/dist');
mkdirSync(out, { recursive: true });
const port = 4180;
const srv = spawn('node', ['serve.mjs', dist, String(port)], { stdio: ['ignore', 'ignore', 'inherit'] });
await new Promise((r) => setTimeout(r, 1200));
const base = `http://127.0.0.1:${port}`;

const desktop = [
  ['signin', '/', { signedOut: true }],
  ['home', '/'],
  ['launchpad', '/', { launchpad: true }],
  ['market', '/market'],
  ['app', '/market/uptime-kuma'],
  ['approvals', '/approvals'],
  ['activity', '/activity'],
  ['settings', '/settings'],
  ['nodes', '/nodes'],
  ['storage', '/storage'],
  ['backups', '/backups'],
];
const phone = [
  ['home', '/'],
  ['market', '/market'],
  ['approvals', '/approvals'],
];

const browser = await chromium.launch();
async function shoot(name, path, form, theme, size, opts = {}) {
  const ctx = await browser.newContext({
    viewport: size,
    deviceScaleFactor: form === 'phone' ? 2 : 1,
    colorScheme: theme,
    locale: 'en-US',
    timezoneId: 'America/New_York',
  });
  const page = await ctx.newPage();
  await page.clock.setFixedTime(new Date('2026-11-12T19:05:00Z'));
  if (!opts.signedOut) await page.addInitScript(() => window.sessionStorage.setItem('onemind.token', 'owner-demo'));
  await page.goto(base + path);
  await page.locator(opts.signedOut ? 'form' : 'h1, .omh-greeting').first().waitFor({ timeout: 15000 }).catch(() => {});
  await page.getByRole('status').filter({ hasText: /^Loading / }).first().waitFor({ state: 'detached', timeout: 8000 }).catch(() => {});
  if (opts.launchpad) await page.keyboard.press('Control+/');
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise((r) => setTimeout(r, 700));
  });
  await page.screenshot({ path: `${out}/${name}-${form}-${theme}.png` });
  await ctx.close();
}
for (const theme of ['light', 'dark']) {
  for (const [n, p, o] of desktop) await shoot(n, p, 'desktop', theme, { width: 1440, height: 900 }, o);
  for (const [n, p, o] of phone) await shoot(n, p, 'phone', theme, { width: 390, height: 844 }, o);
}
await browser.close();
srv.kill();
