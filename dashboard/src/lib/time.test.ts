// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { effectiveStatus, formatAgo, formatIn, hubNow, secondsSince } from './time';

const NOW = Date.parse('2026-11-11T22:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();

describe('time helpers', () => {
  it('formats ages', () => {
    expect(formatAgo(5)).toBe('5s ago');
    expect(formatAgo(125)).toBe('2m ago');
    expect(formatAgo(7200)).toBe('2h ago');
    expect(formatAgo(null)).toBe('unknown');
    expect(secondsSince('garbage', NOW)).toBeNull();
  });

  it('formats expiry', () => {
    expect(formatIn(new Date(NOW + 90_000).toISOString(), NOW)).toBe('in 1m');
    expect(formatIn(ago(1), NOW)).toBe('expired');
  });

  it('applies the §3 thresholds against hub time (30 s stale, 120 s offline)', () => {
    const f = { fetchedAt: NOW, hubOffsetMs: 0 };
    expect(effectiveStatus('online', ago(5), NOW, f)).toBe('online');
    expect(effectiveStatus('online', ago(30), NOW, f)).toBe('stale');
    expect(effectiveStatus('online', ago(120), NOW, f)).toBe('offline');
  });

  it('is not fooled by a skewed browser clock', () => {
    const fast = NOW + 10 * 60_000; // browser runs 10 min ahead of the hub
    const f = { fetchedAt: fast, hubOffsetMs: NOW - fast };
    expect(effectiveStatus('online', ago(5), fast, f)).toBe('online');
    expect(secondsSince(ago(5), hubNow(fast, f))).toBe(5);
    // Without a hub clock, last_seen is not compared with the browser clock at all.
    expect(effectiveStatus('online', ago(5), fast, { fetchedAt: fast })).toBe('online');
    // A slow browser clock cannot make a stale node look live either.
    const slow = NOW - 10 * 60_000;
    expect(effectiveStatus('online', ago(40), slow, { fetchedAt: slow, hubOffsetMs: NOW - slow })).toBe('stale');
  });

  it('ages the gateway answer by the time since it was fetched', () => {
    expect(effectiveStatus('online', ago(5), NOW + 29_000, { fetchedAt: NOW })).toBe('online');
    expect(effectiveStatus('online', ago(5), NOW + 30_000, { fetchedAt: NOW })).toBe('stale');
    expect(effectiveStatus('online', ago(5), NOW + 120_000, { fetchedAt: NOW })).toBe('offline');
  });

  it('never upgrades a status the gateway reported as worse', () => {
    expect(effectiveStatus('offline', ago(1), NOW, { fetchedAt: NOW, hubOffsetMs: 0 })).toBe('offline');
    expect(effectiveStatus('stale', ago(1), NOW, { fetchedAt: NOW, hubOffsetMs: 0 })).toBe('stale');
  });

  it('treats an unparseable last_seen as offline', () => {
    expect(effectiveStatus('online', 'nope', NOW)).toBe('offline');
  });
});
