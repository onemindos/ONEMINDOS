// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { freshness } from './freshness';
import { formatAgo, formatIn } from './time';
import { installBlockReason, safeHttpUrl } from './trust';
import { applyTheme, storedTheme } from './theme';

const NOW = Date.parse('2026-11-12T15:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();

describe('freshness (contract §3: stale after 30 s, offline after 120 s)', () => {
  it.each([
    [0, 'live'],
    [30, 'live'],
    [31, 'stale'],
    [120, 'stale'],
    [121, 'offline'],
    [Number.NaN, 'unknown'],
  ])('%s s → %s', (age, want) => expect(freshness(age)).toBe(want));
});

describe('time', () => {
  it('formats ages and deadlines', () => {
    expect(formatAgo(3)).toBe('just now');
    expect(formatAgo(42)).toBe('42 s ago');
    expect(formatAgo(300)).toBe('5 min ago');
    expect(formatAgo(7200)).toBe('2 h ago');
    expect(formatIn(new Date(NOW + 3600_000 * 5).toISOString(), NOW)).toBe('in 5 h');
    expect(formatIn(ago(1), NOW)).toBe('expired');
  });
});

describe('install gate (§10.3 / §11.1)', () => {
  it('allows a passing scan from this week', () => {
    expect(installBlockReason({ scanned_at: ago(86_400), result: 'pass' }, 'verified', NOW)).toBeUndefined();
  });
  it('blocks missing, failed, stale, future-dated scans and blocked tier', () => {
    expect(installBlockReason(null, 'verified', NOW)).toMatch(/Not scanned/);
    expect(installBlockReason({ scanned_at: ago(60), result: 'fail' }, 'verified', NOW)).toMatch(/Failed/);
    expect(installBlockReason({ scanned_at: ago(8 * 86_400), result: 'pass' }, 'verified', NOW)).toMatch(/7 days/);
    expect(installBlockReason({ scanned_at: ago(-3600), result: 'pass' }, 'verified', NOW)).toMatch(/invalid date/);
    expect(installBlockReason({ scanned_at: ago(60), result: 'pass' }, 'blocked', NOW)).toMatch(/Blocked/);
  });
  it('renders only http(s) links', () => {
    expect(safeHttpUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeHttpUrl('data:text/html,x')).toBeUndefined();
    expect(safeHttpUrl('https://example.org/docs')).toBe('https://example.org/docs');
  });
});

describe('theme', () => {
  it('sets and clears data-theme and remembers the choice', () => {
    // A plain in-memory store: newer Node versions ship their own global localStorage.
    const mem = new Map<string, string>();
    vi.stubGlobal('localStorage', { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v) });
    Object.defineProperty(window, 'localStorage', { configurable: true, value: globalThis.localStorage });
    applyTheme('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(storedTheme()).toBe('dark');
    applyTheme('system');
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(storedTheme()).toBe('system');
    vi.unstubAllGlobals();
  });
});
