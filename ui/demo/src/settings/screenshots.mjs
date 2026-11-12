// SPDX-License-Identifier: Apache-2.0
// Screenshots of the Settings, Activity and Approvals screens into docs/design/screens/settings/:
// every screen in light and dark, desktop (1280) and phone (390), plus each async state once.
// Playwright is not a dependency of this package: install it outside the repo, then
//   npx vite build --config vite.demo.config.ts --outDir <dir>
//   NODE_PATH=<prefix>/node_modules node demo/src/settings/screenshots.mjs <dir>
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { extname, join, resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const root = resolve(process.argv[2] ?? new URL('../../../dist-demo', import.meta.url).pathname);
const out = resolve(new URL('../../../../docs/design/screens/settings', import.meta.url).pathname);
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

const SECTIONS = ['account', 'users', 'agents', 'devices', 'network', 'storage', 'backups', 'updates', 'notifications', 'automation', 'about'];
const SCREENS = [...SECTIONS.map((s) => `system/${s}`), 'system/activity', 'system/approvals'];

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
async function shoot(theme, viewport, routes, suffix, { fullPage = true, state } = {}) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: theme, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  for (const s of routes) {
    await page.goto(`${base}?theme=${theme}${state ? `&state=${state}` : ''}#/${s}`);
    await page.waitForSelector('h1');
    // Full-page phone shots: pin the tab bar to the page bottom so it does not cover content mid-page.
    if (fullPage && viewport.width < 720) await page.addStyleTag({ content: 'body { position: relative; } .om-tabbar { position: absolute !important; }' });
    await page.waitForTimeout(80);
    const name = `${s.replace('system/', '').replace('system', 'index')}${suffix}.png`;
    await page.screenshot({ path: join(out, name), fullPage });
    console.log(name);
  }
  await ctx.close();
}
const desk = { width: 1280, height: 860 };
const phone = { width: 390, height: 844 };
await shoot('light', desk, SCREENS, '');
await shoot('dark', desk, SCREENS, '-dark');
await shoot('light', phone, ['system', ...SCREENS], '-phone');
await shoot('dark', phone, ['system', ...SCREENS], '-phone-dark');
for (const state of ['loading', 'error', 'stale', 'empty']) {
  await shoot('light', desk, ['system/backups', 'system/approvals'], `-${state}`, { state });
}
await browser.close();
server.close();
