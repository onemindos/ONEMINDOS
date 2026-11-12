// SPDX-License-Identifier: Apache-2.0
// After the library build: copy the token values to dist/tokens.json for non-CSS consumers.
// Reads the built library so it needs no TypeScript runtime.
import { writeFileSync } from 'node:fs';

const mod = await import(new URL('../dist/onemind-ui.js', import.meta.url).href).catch(() => null);
if (!mod?.tokensJson) {
  console.error('dist/onemind-ui.js has no tokensJson export; run vite build first');
  process.exit(1);
}
writeFileSync(new URL('../dist/tokens.json', import.meta.url), mod.tokensJson());
console.log('wrote dist/tokens.json');
