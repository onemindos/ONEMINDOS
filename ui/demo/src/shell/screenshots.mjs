// SPDX-License-Identifier: Apache-2.0
// Screenshots of the shell demo screens into docs/design/screens/shell/, light and dark,
// desktop (1280 x 860) and phone (390 x 844). Playwright is not a dependency of this package:
//   npm i --prefix <dir> playwright && npx --prefix <dir> playwright install chromium
//   npm run build:demo && NODE_PATH=<dir>/node_modules node demo/src/shell/screenshots.mjs [dist-demo dir]
// Set PW_CHANNEL=chrome to use an installed Google Chrome instead.
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { extname, join, resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const here = new URL('.', import.meta.url).pathname;
const root = resolve(process.argv[2] ?? join(here, '../../../dist-demo'));
const out = resolve(join(here, '../../../../docs/design/screens/shell'));
await mkdir(out, { recursive: true });
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };

const server = createServer(async (req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const file = join(root, path === '/' ? 'index.html' : path);
  if (!file.startsWith(root)) return res.writeHead(403).end();
  try {
    const body = await readFile(file);
    res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' }).end(body);
  } catch {
    res.writeHead(404).end();
  }
}).listen(0, '127.0.0.1');
await new Promise((r) => server.once('listening', r));
const base = `http://127.0.0.1:${server.address().port}/`;

// [route, file name, full page on desktop]
const SCREENS = [
  ['palette', 'palette', false],
  ['palette-search', 'palette-search', false],
  ['notifications', 'notifications', false],
  ['toasts', 'toasts', false],
  ['states', 'states', true],
  ['onboarding-1', 'onboarding-1-box', false],
  ['onboarding-2', 'onboarding-2-owner', false],
  ['onboarding-3', 'onboarding-3-appearance', false],
  ['onboarding-4', 'onboarding-4-apps', false],
  ['onboarding-5', 'onboarding-5-backups', false],
  ['onboarding-6', 'onboarding-6-done', false],
];

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
async function shoot(theme, viewport, suffix, phone) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: theme, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  for (const [route, name, full] of SCREENS) {
    // Fresh document per screen so toasts and open popovers never leak between shots.
    await page.goto('about:blank');
    await page.goto(`${base}?theme=${theme}#/shell/${route}`);
    await page.waitForSelector('h1');
    await page.waitForTimeout(150);
    const file = `${name}${suffix}.png`;
    await page.screenshot({ path: join(out, file), fullPage: full && !phone });
    console.log(file);
  }
  await ctx.close();
}
await shoot('light', { width: 1280, height: 860 }, '', false);
await shoot('dark', { width: 1280, height: 860 }, '-dark', false);
await shoot('light', { width: 390, height: 844 }, '-phone', true);
await shoot('dark', { width: 390, height: 844 }, '-phone-dark', true);
await browser.close();
server.close();
