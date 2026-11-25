// SPDX-License-Identifier: Apache-2.0
/**
 * Keeps three.js out of the dashboard's main bundle (issue #814). Runs after `vite build` (the npm
 * "build" script) on dist/: the chunks a first page load fetches are the entry scripts and module
 * preloads named in index.html plus every chunk they import statically. None of them may carry
 * three.js, and three.js must be in the build (in a lazy chunk), so the check can never pass empty.
 *
 * three.js marks itself with `window.__THREE__ = REVISION`, a property name minifying keeps.
 *
 *   node src/screens/spatial/bundle-check.mjs [dist]     exit 0 clean, 1 with one line per problem
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join, posix, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

export const THREE_MARKER = '__THREE__';
const STATIC_IMPORT = /\b(?:import|export)\s*(?:[\w$*{}\s,]*?\s*from\s*)?["'](\.{1,2}\/[^"']+\.js)["']/g;
const ENTRY = /<script\b[^>]*\btype=["']module["'][^>]*\bsrc=["']([^"']+)["']/g;
const PRELOAD = /<link\b[^>]*\brel=["']modulepreload["'][^>]*\bhref=["']([^"']+)["']/g;

/** dist-relative path of a URL in index.html ("/assets/a.js" or "./assets/a.js" -> "assets/a.js"). */
const fromHtml = url => posix.normalize(url.replace(/^\.?\//, ''));

/**
 * files: dist-relative path -> text, at least index.html and the .js chunks.
 * Returns the eager chunks, the chunks carrying three.js, and the problems (empty when clean).
 */
export function checkBundle(files) {
  const html = files['index.html'];
  if (html === undefined) return { eager: [], three: [], problems: ['index.html is missing: run vite build first'] };
  const queue = [...html.matchAll(ENTRY), ...html.matchAll(PRELOAD)].map(m => fromHtml(m[1]));
  const eager = new Set();
  const problems = [];
  if (queue.length === 0) problems.push('index.html names no module script');
  while (queue.length) {
    const file = queue.shift();
    if (eager.has(file)) continue;
    eager.add(file);
    const code = files[file];
    if (code === undefined) { problems.push(`${file} is named by the build but missing`); continue; }
    for (const m of code.matchAll(STATIC_IMPORT)) queue.push(posix.normalize(posix.join(posix.dirname(file), m[1])));
  }
  const three = Object.keys(files).filter(f => f.endsWith('.js') && files[f].includes(THREE_MARKER)).sort();
  for (const f of three) if (eager.has(f)) problems.push(`three.js is in ${f}, which every page loads: import it only from the lazy /spatial engine`);
  if (three.length === 0) problems.push('no chunk carries three.js: the spatial engine is missing from the build');
  return { eager: [...eager].sort(), three, problems };
}

function readDist(dir) {
  const files = {};
  const walk = d => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.(html|js)$/.test(e.name)) files[relative(dir, p).split(sep).join('/')] = readFileSync(p, 'utf8');
    }
  };
  walk(dir);
  return files;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const dist = process.argv[2] ?? 'dist';
  const { eager, three, problems } = checkBundle(readDist(dist));
  if (problems.length) {
    for (const p of problems) console.error(`bundle-check: ${p}`);
    process.exit(1);
  }
  console.log(`bundle-check: three.js only in lazy ${three.join(', ')}; ${eager.length} eager chunk(s) clean`);
}
