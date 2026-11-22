// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { appState, type AppStateInput, type Fact } from './appState';

const now = Date.parse('2026-11-21T12:00:00Z');
const ok = <T,>(value: T): Fact<T> => ({ state: 'ok', value });
const fresh = { scanned_at: '2026-11-20T12:00:00Z', result: 'pass' as const };
const good: AppStateInput = {
  status: ok('installed'),
  health: ok({ state: 'healthy', reason: null, restarts: 0 }),
  scan: ok(fresh),
  update: { state: 'absent' },
};
const with_ = (patch: Partial<AppStateInput>) => appState({ ...good, ...patch }, now);

describe('app state dot', () => {
  it('is green only when every source answered and none is wrong', () => {
    expect(with_({})).toEqual({ dot: 'ok', label: 'Healthy', reasons: [] });
    expect(with_({ update: ok(false) }).dot).toBe('ok');
  });

  it('turns grey (unknown) for every source that failed, never green', () => {
    for (const k of ['status', 'health', 'scan', 'update'] as const) {
      expect(with_({ [k]: { state: 'failed' } }).dot).toBe('unknown');
    }
    expect(with_({ status: { state: 'absent' } }).dot).toBe('unknown');
    expect(with_({ health: ok({ state: 'unknown', reason: 'no Kubernetes API on this box', restarts: 0 }) }).reasons[0]).toContain('no Kubernetes API');
  });

  it('a known fault outranks an unread fact; unread outranks a warning', () => {
    expect(with_({ health: ok({ state: 'unhealthy', reason: 'web: CrashLoopBackOff', restarts: 5 }), scan: { state: 'failed' } }).dot).toBe('bad');
    expect(with_({ scan: { state: 'failed' }, update: ok(true) }).dot).toBe('unknown');
  });

  it('flags a failed app, a failed scan, many restarts, a stale or missing scan and a waiting update', () => {
    expect(with_({ status: ok('failed') }).dot).toBe('bad');
    expect(with_({ scan: ok({ ...fresh, result: 'fail' }) }).dot).toBe('bad');
    expect(with_({ health: ok({ state: 'healthy', reason: null, restarts: 3 }) })).toMatchObject({ dot: 'warn', reasons: ['It has restarted 3 times.'] });
    expect(with_({ health: ok({ state: 'healthy', reason: null, restarts: 2 }) }).dot).toBe('ok');
    expect(with_({ scan: ok({ ...fresh, scanned_at: '2026-11-10T00:00:00Z' }) }).reasons).toEqual(['Its last scan is more than 7 days old.']);
    expect(with_({ scan: ok(null) }).reasons).toEqual(['It has never been scanned.']);
    expect(with_({ update: ok(true) }).dot).toBe('warn');
    expect(with_({ status: ok('updating') }).dot).toBe('warn');
  });

  it('a stopped app is grey-neutral, not a fault', () => {
    expect(with_({ status: ok('stopped'), health: ok({ state: 'stopped', reason: 'no pods are running', restarts: 0 }) })).toMatchObject({ dot: 'neutral', label: 'Stopped' });
  });
});
