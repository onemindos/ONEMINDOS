// SPDX-License-Identifier: Apache-2.0
// Tiny static server for a built single-page app (no dependencies), started by playwright.config.ts.
//   node serve.mjs <dist dir> <port>
// Unknown paths without a file extension fall back to index.html, like the gateway's SPA
// fallback (contract §3 "Static"), so the dashboard's BrowserRouter paths load directly.
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, resolve, sep } from 'node:path';

const root = resolve(process.argv[2] ?? '.');
const port = Number(process.argv[3] ?? 4173);
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
  '.ico': 'image/x-icon',
};

async function isFile(p) {
  try {
    return (await stat(p)).isFile();
  } catch {
    return false;
  }
}

await stat(join(root, 'index.html')).catch(() => {
  console.error(`serve.mjs: ${root}/index.html not found; build first (see ui/test/README.md)`);
  process.exit(2);
});

createServer(async (req, res) => {
  const path = decodeURIComponent(new URL(req.url ?? '/', 'http://x').pathname);
  let file = resolve(join(root, path));
  if (file !== root && !file.startsWith(root + sep)) return res.writeHead(403).end();
  if (!(await isFile(file))) {
    if (await isFile(join(file, 'index.html'))) file = join(file, 'index.html');
    else if (!extname(path)) file = join(root, 'index.html');
    else return res.writeHead(404).end();
  }
  const body = await readFile(file);
  res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream', 'cache-control': 'no-store' }).end(body);
}).listen(port, '127.0.0.1', () => console.log(`serving ${root} on http://127.0.0.1:${port}/`));
