// SPDX-License-Identifier: Apache-2.0
// Screenshots of the Home launcher into docs/design/screens/home/, light and dark, desktop
// and phone. Playwright is not a dependency of this package: install it outside the repo,
//   npm i --prefix <dir> playwright && npx --prefix <dir> playwright install chromium
//   npm run build:demo && NODE_PATH=<dir>/node_modules node demo/src/home/shoot.mjs
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { extname, join, resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const root = resolve(new URL('../../../dist-demo', import.meta.url).pathname);
const out = resolve(new URL('../../../../docs/design/screens/home', import.meta.url).pathname);
await mkdir(out, { recursive: true });
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };

const server = createServer(async (req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const file = join(root, path === '/' ? 'index.html' : path);
  if (!file.startsWith(root)) return res.writeHead(403).end();
  let body;
  try {
    body = await readFile(file);
  } catch {
    return res.writeHead(404).end();
  }
  res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' }).end(body);
}).listen(0, '127.0.0.1');
await new Promise((r) => server.once('listening', r));
const base = `http://127.0.0.1:${server.address().port}/`;

// [file name, hash route, optional step after load]
const SHOTS = [
  ['home', 'home'],
  ['home-edit', 'home/edit'],
  ['home-gallery', 'home/edit', async (p) => p.getByRole('button', { name: 'Add widget' }).click()],
  ['home-search', 'home', async (p) => p.getByRole('button', { name: /Search apps, nodes and settings/ }).click()],
  ['home-offline', 'home/offline'],
  ['home-loading', 'home/loading'],
  ['home-errors', 'home/errors'],
  ['home-fresh', 'home/fresh'],
];
const VIEWPORTS = [
  ['', { width: 1280, height: 860 }],
  ['-phone', { width: 390, height: 844 }],
];

// PW_CHANNEL=chromium uses the full Chromium build instead of the headless shell.
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
for (const theme of ['light', 'dark']) {
  for (const [suffix, viewport] of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: theme, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    for (const [name, route, step] of SHOTS) {
      await page.goto(`${base}?theme=${theme}#/${route}`);
      await page.reload();
      await page.waitForSelector('h1');
      if (step) await step(page);
      await page.waitForTimeout(150);
      const file = `${name}${suffix}${theme === 'dark' ? '-dark' : ''}.png`;
      // Dialogs are shown at screen height. Pages are shot in full with the viewport grown to
      // the page height, so the sticky dock and fixed tab bar sit at the bottom as a person sees them.
      if (step) await page.screenshot({ path: join(out, file) });
      else {
        const height = await page.evaluate(() => document.documentElement.scrollHeight);
        await page.setViewportSize({ width: viewport.width, height });
        // Let layout and paint settle after the resize, or the shot repeats the top of the page.
        await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
        await page.waitForTimeout(250);
        await page.screenshot({ path: join(out, file) });
        await page.setViewportSize(viewport);
      }
      console.log(file);
    }
    await ctx.close();
  }
}
await browser.close();
server.close();
