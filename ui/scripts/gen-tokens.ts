// SPDX-License-Identifier: Apache-2.0
// Writes src/tokens/tokens.css from src/tokens/tokens.ts. Run: npm run tokens
import { writeFileSync } from 'node:fs';
import { toCss } from '../src/tokens/tokens.ts';

const out = new URL('../src/tokens/tokens.css', import.meta.url);
writeFileSync(out, toCss());
console.log(`wrote ${out.pathname.split('/ui/')[1] ?? out.pathname}`);
