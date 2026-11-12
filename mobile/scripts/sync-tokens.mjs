// SPDX-License-Identifier: Apache-2.0
// Copies the design tokens from the one source of truth (ui/src/tokens/tokens.ts, docs/design/TOKENS.md)
// into src/ui/tokens.generated.ts, so the phone app uses exactly the dashboard's colours, spacing and radii.
//   npm run tokens          write the file
//   npm run tokens -- --check   exit 1 if it is out of date (src/ui/tokens.test.ts runs the same comparison)
import { readFileSync, writeFileSync } from 'node:fs';

const src = new URL('../../ui/src/tokens/tokens.ts', import.meta.url);
const out = new URL('../src/ui/tokens.generated.ts', import.meta.url);
const mod = await import(src.href);
const { palette, light, dark, scale, shadow } = JSON.parse(mod.toJson());
const text =
  '// SPDX-License-Identifier: Apache-2.0\n' +
  '// Generated from ui/src/tokens/tokens.ts by `npm run tokens` in mobile/. Do not edit by hand.\n' +
  `export const tokens = ${JSON.stringify({ palette, light, dark, scale, shadow }, null, 2)} as const;\n`;

if (process.argv.includes('--check')) {
  let current = '';
  try {
    current = readFileSync(out, 'utf8');
  } catch {
    /* missing */
  }
  if (current !== text) {
    console.error('src/ui/tokens.generated.ts is out of date: run `npm run tokens` in mobile/');
    process.exit(1);
  }
  console.log('tokens up to date');
} else {
  writeFileSync(out, text);
  console.log('wrote src/ui/tokens.generated.ts');
}
