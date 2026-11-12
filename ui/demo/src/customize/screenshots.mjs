// SPDX-License-Identifier: Apache-2.0
// Screenshots of the Appearance screen states into docs/design/screens/customize/,
// light and dark, desktop (1280 px) and phone (390 px). Playwright is not a dependency:
//   npm i --prefix <dir> playwright && npx --prefix <dir> playwright install chromium
//   npx vite build --config vite.demo.config.ts --outDir <demo-dir>
//   NODE_PATH=<dir>/node_modules node demo/src/customize/screenshots.mjs <demo-dir>
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { extname, join, resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const root = resolve(process.argv[2] ?? new URL('../../../dist-demo', import.meta.url).pathname);
const out = resolve(new URL('../../../../docs/design/screens/customize', import.meta.url).pathname);
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

const STATES = ['synced', 'custom', 'stale', 'empty', 'loading', 'error'];
const VIEWS = [
  // Desktop: the viewport grows to the page height, so the fixed wallpaper covers the whole shot.
  // Phone: one screen-height shot, so the fixed tab bar sits where a person sees it.
  ['desktop', { width: 1280, height: 860 }, true],
  ['phone', { width: 390, height: 844 }, false],
];

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
for (const theme of ['light', 'dark']) {
  for (const [view, viewport, fullPage] of VIEWS) {
    const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: theme, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    for (const s of STATES) {
      await page.goto(`${base}?theme=${theme}#/appearance/${s}`);
      await page.waitForSelector('h1');
      await page.waitForTimeout(150);
      const name = `appearance-${s}-${view}-${theme}.png`;
      await page.setViewportSize(viewport);
      if (fullPage) {
        const h = await page.evaluate(() => document.documentElement.scrollHeight);
        await page.setViewportSize({ width: viewport.width, height: Math.max(viewport.height, h) });
        // Let layout and paint settle after the resize; without this the shots came out half blank.
        await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
        await page.waitForTimeout(250);
      }
      await page.screenshot({ path: join(out, name) });
      console.log(name);
    }
    await ctx.close();
  }
}
await browser.close();
server.close();
