// SPDX-License-Identifier: Apache-2.0
// The phone's copy of the design tokens must match ui/src/tokens/tokens.ts (the one source of truth).
// Plain JS: it only runs the sync script's --check mode in Node.
const { execFileSync } = require('node:child_process');
const { join } = require('node:path');

describe('design tokens', () => {
  it('match @onemind/ui exactly (run `npm run tokens` in mobile/ after a token change)', () => {
    const script = join(__dirname, '../../scripts/sync-tokens.mjs');
    const out = execFileSync(process.execPath, ['--experimental-strip-types', '--no-warnings', script, '--check'], { encoding: 'utf8' });
    expect(out).toMatch(/up to date/);
  });
});
