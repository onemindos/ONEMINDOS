// SPDX-License-Identifier: Apache-2.0
// Screenshots of the App Store screens into docs/design/screens/store/, light and dark,
// desktop (1280 px) and phone (390 px). Playwright is not a dependency:
//   npm i --prefix <dir> playwright && npx --prefix <dir> playwright install chromium
//   npx vite build --config vite.demo.config.ts --outDir <demo-dir>
//   NODE_PATH=<dir>/node_modules node demo/src/store/screenshots.mjs <demo-dir> [name ...]
// Set PW_CHANNEL=chrome to use an installed Google Chrome. Names limit the run to those shots.
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { extname, join, resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const root = resolve(process.argv[2] ?? new URL('../../../dist-demo', import.meta.url).pathname);
const only = new Set(process.argv.slice(3));
const out = resolve(new URL('../../../../docs/design/screens/store', import.meta.url).pathname);
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

// [name, route, state, action]; action runs after load (e.g. open a dialog).
const SHOTS = [
  ['discover', 'store', '', null],
  ['installed', 'store/installed', '', null],
  ['updates', 'store/updates', '', null],
  ['manage', 'store/manage/home-assistant', '', null],
  ['app-immich', 'store/app/immich', '', null],
  ['install-review', 'store/app/immich', '', async (page) => page.getByRole('button', { name: /^Request install/ }).first().click()],
];

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
for (const theme of ['light', 'dark']) {
  for (const [view, viewport] of [['', { width: 1280, height: 860 }], ['-phone', { width: 390, height: 844 }]]) {
    const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: theme, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    for (const [name, route, state, action] of SHOTS) {
      if (only.size && !only.has(name)) continue;
      await page.goto(`${base}?theme=${theme}${state ? `&state=${state}` : ''}#/${route}`);
      await page.reload();
      await page.waitForSelector('h1');
      if (action) await action(page);
      await page.waitForTimeout(200);
      // Desktop: whole page for browsing screens; dialogs and phones: one screen, as a person sees it.
      const full = view === '' && !action;
      const file = `${name}${theme === 'dark' ? '-dark' : ''}${view}.png`;
      await page.screenshot({ path: join(out, file), fullPage: full });
      console.log(file);
    }
    await ctx.close();
  }
}
await browser.close();
server.close();
