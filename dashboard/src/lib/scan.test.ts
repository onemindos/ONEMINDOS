// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { formatDay, installBlockReason, safeHttpUrl } from './scan';

const NOW = Date.parse('2026-11-12T12:00:00Z');
const at = (msAgo: number) => new Date(NOW - msAgo).toISOString();
const DAY = 86_400_000;

describe('installBlockReason (§10.3)', () => {
  it('allows a passing scan up to 7 days old', () => {
    expect(installBlockReason({ scan: { scanned_at: at(DAY), result: 'pass' } }, NOW)).toBeUndefined();
    expect(installBlockReason({ scan: { scanned_at: at(7 * DAY), result: 'pass' } }, NOW)).toBeUndefined();
  });

  it('blocks a missing, failing, stale or future-dated scan, with a reason', () => {
    expect(installBlockReason({ scan: null }, NOW)).toMatch(/Not scanned yet/);
    expect(installBlockReason({ scan: { scanned_at: at(DAY), result: 'fail' } }, NOW)).toMatch(/Failed its last/);
    expect(installBlockReason({ scan: { scanned_at: at(7 * DAY + 1000), result: 'pass' } }, NOW)).toMatch(
      /more than 7 days ago/,
    );
    expect(installBlockReason({ scan: { scanned_at: at(-DAY), result: 'pass' } }, NOW)).toMatch(/invalid date/);
    expect(installBlockReason({ scan: { scanned_at: 'yesterday', result: 'pass' } }, NOW)).toMatch(/invalid date/);
  });
});

describe('helpers', () => {
  it('formats the scan day in UTC', () => {
    expect(formatDay('2026-11-10T23:30:00Z')).toBe('10 Nov 2026');
  });

  it('only lets http(s) links through', () => {
    expect(safeHttpUrl('https://example.com/docs')).toBe('https://example.com/docs');
    expect(safeHttpUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeHttpUrl('data:text/html,x')).toBeUndefined();
    expect(safeHttpUrl('not a url')).toBeUndefined();
    expect(safeHttpUrl(null)).toBeUndefined();
  });
});
