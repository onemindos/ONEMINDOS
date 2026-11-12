// SPDX-License-Identifier: Apache-2.0
// Keeps src/tokens.css an exact copy of ui/src/tokens/tokens.css (the OneMind design tokens; their
// accent follows brand/brand.json through scripts/brand-sync.py), with line 2 naming the source.
//   node tools/tokens.mjs           write the copy   (npm run sync:tokens)
//   node tools/tokens.mjs --check   exit 1 if it is out of date (npm run check:ui, CI)
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const at = (p) => fileURLToPath(new URL(p, import.meta.url));
const SRC = at('../../ui/src/tokens/tokens.css');
const DST = at('../src/tokens.css');
const NOTE = '/* Copied from ui/src/tokens/tokens.css by `npm run sync:tokens` (OneMind design tokens). Do not edit by hand. */';
// Windows checkouts may use CRLF; compare and write with LF.
const read = (p) => readFileSync(p, 'utf8').replace(/\r\n/g, '\n');

const lines = read(SRC).split('\n');
lines[1] = NOTE;
const want = lines.join('\n');
let have = '';
try {
  have = read(DST);
} catch {
  have = '';
}
if (process.argv.includes('--check')) {
  if (have !== want) {
    console.error('desktop/src/tokens.css is out of date: run `npm run sync:tokens` in desktop/ and commit it');
    process.exit(1);
  }
  console.log('src/tokens.css matches ui/src/tokens/tokens.css');
} else if (have !== want) {
  writeFileSync(DST, want);
  console.log('wrote src/tokens.css');
} else {
  console.log('src/tokens.css is up to date');
}
