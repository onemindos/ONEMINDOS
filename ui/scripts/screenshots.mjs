// SPDX-License-Identifier: Apache-2.0
// Screenshots of every demo screen into docs/design/screens/ (headless Chromium via Playwright).
// Playwright is not a dependency of this package: install it outside the repo, e.g.
//   npm i --prefix /tmp/pw playwright && npx --prefix /tmp/pw playwright install chromium
//   NODE_PATH=/tmp/pw/node_modules node scripts/screenshots.mjs [dist-demo dir]
// Set PW_CHANNEL=chrome to use an installed Google Chrome instead of the downloaded Chromium.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { extname, join, resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const root = resolve(process.argv[2] ?? new URL('../dist-demo', import.meta.url).pathname);
const out = resolve(new URL('../../docs/design/screens', import.meta.url).pathname);
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

const SCREENS = ['home', 'apps', 'app/home-assistant', 'app/immich', 'approvals', 'activity', 'nodes', 'backups', 'updates', 'notifications', 'settings', 'gallery'];
const DARK = ['home', 'approvals', 'nodes', 'app/home-assistant', 'gallery'];
const PHONE = ['home', 'approvals', 'nodes', 'activity', 'notifications', 'app/home-assistant'];

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
async function shoot(theme, viewport, screens, suffix, fullPage = true) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: theme, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  for (const s of screens) {
    await page.goto(`${base}?theme=${theme}#/${s}`);
    await page.waitForSelector('h1');
    const name = `${s.replace('/', '-')}${suffix}.png`;
    await page.screenshot({ path: join(out, name), fullPage });
    console.log(name);
  }
  await ctx.close();
}
await shoot('light', { width: 1280, height: 860 }, SCREENS, '');
await shoot('dark', { width: 1280, height: 860 }, DARK, '-dark');
// Phones: one screen-height shot, so the fixed tab bar sits where a person sees it.
await shoot('light', { width: 390, height: 844 }, PHONE, '-phone', false);
await shoot('dark', { width: 390, height: 844 }, ['approvals'], '-phone-dark', false);
await browser.close();
server.close();
