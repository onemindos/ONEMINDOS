// SPDX-License-Identifier: Apache-2.0
import type { StatusView } from '../api/types';
import status from '../test/status.recorded.json';
import { appOpenUrl, healthRows, healthState, liveIndicator } from './health';

const NOW = Date.parse('2026-11-22T12:00:00+00:00');

describe('health rows from a recorded /v1/status', () => {
  const rows = healthRows(status as unknown as StatusView, NOW);
  const by = (k: string) => rows.find((r) => r.source === k)!;

  it('has one row per source', () => {
    expect(rows.map((r) => r.source)).toEqual(['alerts', 'approvals', 'apps', 'storage', 'backups', 'updates', 'mesh']);
  });

  it('shows an unknown source as unknown, never ok', () => {
    expect(by('storage').state).toBe('unknown');
    expect(by('storage').age).toBe('unknown');
  });

  it('shows a state it does not recognise as unknown, never ok', () => {
    expect(healthState('bogus-new-state')).toBe('unknown');
    expect(healthState(undefined)).toBe('unknown');
    expect(by('mesh').state).toBe('unknown');
  });

  it('shows the age of each read and where a tap goes', () => {
    expect(by('alerts').age).toBe('10s ago');
    expect(by('backups').age).toBe('1h ago');
    expect(by('backups').to).toEqual({ screen: 'Backups' });
    expect(by('approvals').to).toEqual({ tab: 'Approvals' });
    expect(by('updates').to).toEqual({ screen: 'OsUpdates' });
  });
});

describe('live indicator', () => {
  it('follows the stream state', () => {
    expect(liveIndicator('open')).toBe('live');
    expect(liveIndicator('connecting')).toBe('reconnecting');
    expect(liveIndicator('retrying')).toBe('reconnecting');
    expect(liveIndicator('off')).toBe('polling');
    expect(liveIndicator('unsupported')).toBe('polling');
  });
});

describe('Open address', () => {
  it('uses the web port on the box host, only for installed apps', () => {
    expect(appOpenUrl({ installed: true, web_port: 3001 }, 'https://hub.example:8443')).toBe('https://hub.example:3001/');
    expect(appOpenUrl({ installed: false, web_port: 3001 }, 'https://hub.example')).toBeUndefined();
    expect(appOpenUrl({ installed: true, web_port: null }, 'https://hub.example')).toBeUndefined();
    expect(appOpenUrl({ installed: true, web_port: 3001 }, undefined)).toBeUndefined();
    expect(appOpenUrl({ installed: true, web_port: 70000 }, 'https://hub.example')).toBeUndefined();
    expect(appOpenUrl({ installed: true, web_port: 3001 }, 'javascript:alert(1)')).toBeUndefined();
  });
});
