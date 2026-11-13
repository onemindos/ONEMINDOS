// SPDX-License-Identifier: Apache-2.0
// Writes src/tokens/tokens.css from src/tokens/tokens.ts. Run: npm run tokens
// `--check` writes nothing and exits 1 when tokens.css is out of date (scripts/brand-sync.py --check).
import { readFileSync, writeFileSync } from 'node:fs';
import { toCss } from '../src/tokens/tokens.ts';

const out = new URL('../src/tokens/tokens.css', import.meta.url);
const name = out.pathname.split('/ui/')[1] ?? out.pathname;
if (process.argv.includes('--check')) {
  let cur = '';
  try {
    cur = readFileSync(out, 'utf8');
  } catch {
    // missing counts as out of date
  }
  if (cur !== toCss()) {
    console.error(`out of date: ui/${name} (run npm run tokens in ui/)`);
    process.exit(1);
  }
} else {
  writeFileSync(out, toCss());
  console.log(`wrote ${name}`);
}
