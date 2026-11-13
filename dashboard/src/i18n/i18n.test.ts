// SPDX-License-Identifier: Apache-2.0
// Every t('key') in the source exists in en.ts, and no en.ts key is dead.
import { describe, expect, it } from 'vitest';
import { en } from './en';
import { t } from './index';

// Every source file except tests and the catalogue itself, as text.
const files = import.meta.glob(['../**/*.ts', '../**/*.tsx', '!../**/*.test.*', '!../i18n/en.ts'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

describe('i18n scaffold', () => {
  const code = Object.values(files).join('\n');
  const used = new Set([...code.matchAll(/\bt\(\s*'([a-z][\w.]*)'/g)].map((m) => m[1]!));

  it('every key used in code exists', () => {
    expect([...used].filter((k) => !(k in en))).toEqual([]);
  });
  it('every key is used somewhere', () => {
    expect(Object.keys(en).filter((k) => !used.has(k))).toEqual([]);
  });
  it('fills placeholders and leaves unknown ones visible', () => {
    expect(t('users.disable', { name: 'Sam' })).toBe('Disable Sam');
    expect(t('users.disable')).toBe('Disable {name}');
  });
});
