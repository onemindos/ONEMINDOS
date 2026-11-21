// SPDX-License-Identifier: Apache-2.0
// UMB-P13 (#431): a screen that already uses t() may not grow a hard-coded English sentence in
// its markup. Files that do not use t() yet are the migration backlog and are not checked.
import { describe, expect, it } from 'vitest';

const files = import.meta.glob(['../pages/*.tsx', '../shell/*.tsx', '!../**/*.test.*'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

// JSX text with two or more words, e.g. >Save your changes<
const TEXT = />\s*[A-Z][a-z]+(?:\s+[a-z]+)+[^<>{}]*</g;

describe('hard-coded strings', () => {
  it('no JSX sentence in a file that already uses t()', () => {
    const bad: string[] = [];
    for (const [path, code] of Object.entries(files)) {
      if (!/\bt\(\s*'/.test(code)) continue;
      for (const m of code.matchAll(TEXT)) bad.push(`${path}: ${m[0].trim()}`);
    }
    expect(bad).toEqual([]);
  });
  it('the check catches a sentence', () => {
    expect('<p>Save your changes now</p>'.match(TEXT)).not.toBeNull();
    expect("<p>{t('common.save')}</p>".match(TEXT)).toBeNull();
  });
});
