import { describe, expect, it } from 'vitest';
import { effectiveStatus, formatAgo, formatIn, secondsSince } from './time';

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

  it('applies the §3 thresholds locally (30 s stale, 120 s offline)', () => {
    expect(effectiveStatus('online', ago(5), NOW)).toBe('online');
    expect(effectiveStatus('online', ago(30), NOW)).toBe('stale');
    expect(effectiveStatus('online', ago(120), NOW)).toBe('offline');
  });

  it('never upgrades a status the gateway reported as worse', () => {
    expect(effectiveStatus('offline', ago(1), NOW)).toBe('offline');
    expect(effectiveStatus('stale', ago(1), NOW)).toBe('stale');
  });

  it('treats an unparseable last_seen as offline', () => {
    expect(effectiveStatus('online', 'nope', NOW)).toBe('offline');
  });
});
