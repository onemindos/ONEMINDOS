// SPDX-License-Identifier: Apache-2.0
import { makeApps } from '../api/fixtures';
import { ApiError, type BackupDestination } from '../api/types';
import { v0Api } from '../test/fakes';
import { actionTitle, REQUEST_TTL_MS } from './approvals';
import {
  destinationsFor,
  formatBytes,
  isBusy,
  lifecycleOptions,
  previewLifecycle,
  requestError,
  requestLifecycle,
  settingsProblem,
  validBoxName,
} from './manage';

const dests: BackupDestination[] = [
  { id: 'dst_0000000000000001', kind: 'usb', label: 'Blue USB disk' },
  { id: 'dst_0000000000000002', kind: 'box', label: 'Garage box' },
  { id: 'dst_0000000000000003', kind: 's3', label: 'Bucket' },
];
const good = { box_name: 'home', time_zone: 'Europe/Berlin', backup_choice: 'usb' as const, backup_destination_id: 'dst_0000000000000001' };

describe('lifecycle options', () => {
  it('offers what fits the status', () => {
    expect(lifecycleOptions({ installed: true, status: 'installed' })).toEqual(['app.stop', 'app.restart', 'app.update', 'app.remove']);
    expect(lifecycleOptions({ installed: true, status: 'stopped' })).toEqual(['app.start', 'app.remove']);
    expect(lifecycleOptions({ installed: false, status: 'not_installed' })).toEqual([]);
  });
  it('offers nothing while the app is changing', () => {
    for (const s of ['starting', 'stopping', 'restarting', 'updating', 'configuring', 'deleting_data', 'reverting']) {
      expect(isBusy(s)).toBe(true);
      expect(lifecycleOptions({ installed: true, status: s })).toEqual([]);
    }
  });
  it('never offers delete-data from the phone', () => {
    expect(lifecycleOptions({ installed: true, status: 'installed' })).not.toContain('app.delete_data');
  });
  it('titles the new request types for the approval list', () => {
    expect(actionTitle({ type: 'app.restart', params: { app_id: 'ollama' } })).toBe('Restart ollama');
    expect(actionTitle({ type: 'app.update', params: { app_id: 'ollama' } })).toBe('Update ollama');
  });
});

describe('requesting a lifecycle change', () => {
  const NOW = Date.parse('2026-11-13T10:00:00Z');
  it('previews first, then files the request bound to that plan hash', async () => {
    const appPlan = jest.fn(async () => ({ app_id: 'ollama', policy_verdict: 'needs_approval', plan: { summary: 'Restart' }, plan_sha256: 'sha256:abc' }));
    const createAction = jest.fn(async (r) => ({ ...r, id: 'act-1', state: 'awaiting_approval' as const }));
    const api = v0Api({ appPlan, createAction });
    const p = await previewLifecycle(api, 'ollama', 'app.restart');
    expect(p.refused).toBe(false);
    expect(createAction).not.toHaveBeenCalled(); // a preview files nothing
    const a = await requestLifecycle(api, 'ollama', 'app.restart', p.preview.plan_sha256, { now: NOW, idempotencyKey: 'k' });
    expect(a.state).toBe('awaiting_approval');
    expect(createAction).toHaveBeenCalledWith({
      type: 'app.restart',
      params: { app_id: 'ollama' },
      idempotency_key: 'k',
      expires_at: new Date(NOW + REQUEST_TTL_MS).toISOString(),
      plan_sha256: 'sha256:abc',
    });
  });
  it('a refused plan is flagged, so the screen does not offer to send it', async () => {
    const api = v0Api({ appPlan: async () => ({ app_id: 'x', policy_verdict: 'refused', reason: 'not installed', plan: {}, plan_sha256: 'p' }) });
    expect((await previewLifecycle(api, 'x', 'app.start')).refused).toBe(true);
  });
});

describe('request errors', () => {
  it('names the plan change, the owner rule and a busy app in plain words', () => {
    expect(requestError(new ApiError(409, 'stale_precondition', 'm', { reason: 'plan_changed' }), 'the restart').text).toMatch(/plan for the restart changed/);
    expect(requestError(new ApiError(403, 'permission_denied', 'm'), 'that')).toMatchObject({ forbidden: true });
    expect(requestError(new ApiError(409, 'conflict', 'm')).text).toMatch(/busy/);
    expect(requestError(new ApiError(0, 'network', 'offline')).text).toMatch(/Nothing was changed/);
  });
});

describe('first-run settings checks', () => {
  it('accepts a valid body and ties the destination to the choice', () => {
    expect(settingsProblem(good, dests)).toBeUndefined();
    expect(destinationsFor('peer', dests).map((d) => d.label)).toEqual(['Garage box']);
    expect(destinationsFor('later', dests)).toEqual([]);
  });
  it('rejects bad names, zones and mismatched destinations before anything is sent', () => {
    for (const n of ['', 'Home', '-a', 'a-', 'a b', 'x'.repeat(64)]) expect(validBoxName(n)).toBe(false);
    expect(validBoxName('a')).toBe(true);
    expect(settingsProblem({ ...good, box_name: 'Home' }, dests)).toMatch(/lower-case/);
    expect(settingsProblem({ ...good, time_zone: '/etc/localtime' }, dests)).toMatch(/time zone/);
    expect(settingsProblem({ ...good, backup_choice: 's3' }, dests)).toMatch(/does not match/);
    expect(settingsProblem({ ...good, backup_choice: 'later' }, dests)).toMatch(/later/);
  });
});

it('formats sizes', () => {
  expect(formatBytes(null)).toBe('unknown');
  expect(formatBytes(512)).toBe('512 B');
  expect(formatBytes(1_500_000_000)).toBe('1.5 GB');
  // the fixture catalog has an installed app to offer actions on
  expect(makeApps().some((a) => a.installed)).toBe(true);
});
