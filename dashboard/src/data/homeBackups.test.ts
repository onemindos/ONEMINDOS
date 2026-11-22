// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { NO_BACKUPS, toBackupStatus } from './homeBackups';

const AT = '2026-11-21T14:00:00.000Z';

describe('Home backups mapping', () => {
  it('reads what the gateway reports and invents nothing', () => {
    const s = toBackupStatus(
      { health: 'stale', last_success_at: '2026-11-19T02:00:00Z', last_verified_restore_at: null, destinations: [{ label: 'USB disk', kind: 'usb' }, { kind: 'bucket' }] },
      AT,
    );
    expect(s.last_run).toBe('2026-11-19T02:00:00Z');
    expect(s.last_verified_restore).toBeNull();
    expect(s.destinations).toEqual([
      { name: 'USB disk', last_success: '2026-11-19T02:00:00Z', state: 'behind' },
      { name: 'bucket', last_success: '2026-11-19T02:00:00Z', state: 'behind' },
    ]);
  });

  it('maps health to each destination, and ignores timestamps that are not dates', () => {
    expect(toBackupStatus({ health: 'ok', last_success_at: 'soon', destinations: [{ label: 'A' }] }, AT)).toMatchObject({ last_run: null, destinations: [{ state: 'ok' }] });
    expect(toBackupStatus({ health: 'failing', destinations: [{ label: 'A' }] }, AT).destinations[0]?.state).toBe('failing');
    expect(toBackupStatus({ health: 'not_configured' }, AT)).toMatchObject({ destinations: [], last_run: null });
  });

  it('refuses an answer that is not a status object', () => {
    for (const bad of [null, [], 'ok', 3]) expect(() => toBackupStatus(bad, AT)).toThrow(/invalid backup status/);
  });

  it('has an honest empty answer for demo mode', () => {
    expect(NO_BACKUPS(AT)).toEqual({ last_run: null, last_verified_restore: null, destinations: [], observed_at: AT });
  });
});
