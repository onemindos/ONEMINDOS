// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { healthRows } from './healthSummary';

const links = { backups: '/b', alerts: '/a', updates: '/u' };
const now = Date.parse('2026-11-21T12:00:00Z');

describe('health card rows', () => {
  it('says "not reported" when the hub gave no answer, never healthy', () => {
    const rows = healthRows({ backup: undefined, openAlerts: undefined, updates: undefined, now }, links);
    expect(rows.map((r) => [r.value, r.tone])).toEqual([['Not reported', 'neutral'], ['Not reported', 'neutral'], ['Not reported', 'neutral']]);
  });
  it('reports last backup age, critical alerts and an offered update', () => {
    const rows = healthRows({ backup: { last_success_at: '2026-11-21T09:00:00Z', health: 'ok' }, openAlerts: { critical: 2 }, updates: { nodes: [{ available_version: '1.2.0' }, { available_version: '1.2.0' }, {}] }, now }, links);
    expect(rows[0]).toMatchObject({ value: 'Last backup 3h ago', tone: 'ok', href: '/b' });
    expect(rows[1]).toMatchObject({ value: '2 critical alerts open', tone: 'bad', href: '/a' });
    expect(rows[2]).toMatchObject({ value: 'Update available: 1.2.0', tone: 'warn', href: '/u' });
  });
  it('flags a box that never backed up, and a clean one', () => {
    const rows = healthRows({ backup: { health: 'unprotected' }, openAlerts: { critical: 0 }, updates: { nodes: [] }, now }, links);
    expect(rows.map((r) => r.value)).toEqual(['No backup has finished yet', 'No critical alerts', 'Up to date']);
  });
});
