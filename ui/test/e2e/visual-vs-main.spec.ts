// SPDX-License-Identifier: Apache-2.0
// visual-vs-main.sh is the local copy of CI's visual check (ui-quality.yml, CI-17). When the two drift,
// the local run draws a different base than CI does, or none at all: the dashboard mock imports the
// generated SDK schema (CI-16, not committed), so a base built without it has no dashboard screens,
// and dash-market in WebKit showed as "changed" with no reference picture (#883). These checks need
// no browser: they read the two files and fail when the script skips a step CI runs on the base.
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const read = (p: string) => readFileSync(fileURLToPath(new URL(p, import.meta.url)), 'utf8');
const script = read('../visual-vs-main.sh');
const workflow = read('../../../.github/workflows/ui-quality.yml');

/** The body of the script's build() function: what it runs for the base tree and the working tree. */
function buildFunction(): string {
  const m = script.match(/^build\(\) \{[^\n]*\n([\s\S]*?)^\}/m);
  if (!m?.[1]) throw new Error('visual-vs-main.sh has no build() { ... } function');
  return m[1];
}

/** The run: block of the ui-quality.yml step with this name. */
function step(name: string): string {
  const at = workflow.indexOf(`- name: ${name}`);
  if (at < 0) throw new Error(`ui-quality.yml has no step "${name}"`);
  const next = workflow.indexOf('\n      - ', at + 1);
  return workflow.slice(at, next < 0 ? undefined : next);
}

test.describe('visual-vs-main.sh matches CI', () => {
  test('the base build generates the SDK schema before it builds the dashboard, as CI does', () => {
    const ci = step('Build the base (main) the screenshots are compared with');
    expect(ci, 'CI generates the TS schema for the base').toMatch(/sdk\/scripts\/gen-code\.sh ts/);
    const body = buildFunction();
    const gen = body.search(/sdk\/scripts\/gen-code\.sh"? ts/);
    const dash = body.indexOf('npm run build:mock');
    expect(gen, 'build() runs sdk/scripts/gen-code.sh ts').toBeGreaterThanOrEqual(0);
    expect(dash, 'build() builds the dashboard mock').toBeGreaterThanOrEqual(0);
    expect(gen, 'the schema is generated before the dashboard build').toBeLessThan(dash);
    // Old bases (before CI-16) commit the schema and have no script: CI tolerates that, so must we.
    expect(body).toMatch(/\[ -x "\$1\/sdk\/scripts\/gen-code\.sh" \]/);
  });

  test('a base screenshot that fails once is drawn again alone, as CI does', () => {
    const ci = step('Draw the reference screenshots from the base (main)');
    expect(ci).toMatch(/--update-snapshots=all --last-failed/);
    expect(script).toMatch(/--grep @visual --update-snapshots=all --last-failed/);
  });

  test('the default base is the branch PRs merge into (release/next while it exists), as in CI', () => {
    expect(script).toMatch(/origin\/release\/next/);
    const def = script.match(/^base=\$\{1:-(.*)\}$/m);
    expect(def, 'base defaults through a single base= line').not.toBeNull();
    expect(def?.[1]).toMatch(/merge-base HEAD "\$upstream"/);
  });
});
