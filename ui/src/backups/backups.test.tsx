// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { describe, expect, it, vi } from 'vitest';
import { BackupsOverview } from './BackupsOverview';
import { EmergencyKit } from './EmergencyKit';
import {
  badgeView, breadcrumbs, formatBytes, overviewNotice, restoreConfirmed, restoreRequest, snapshotsByDay, typeBackReady, volumeLabel,
} from './logic';
import { RestoreDialog, RestoreProgress } from './RestoreDialog';
import { Rewind } from './Rewind';
import type { BackupsStatus, KitOneTime, KitState, Restore, Snapshot } from './types';

const NOW = Date.parse('2026-11-12T15:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const VOL = '/var/lib/rancher/k3s/storage/pvc-1111_app-notes_data';
const DUMP = '/var/lib/rancher/k3s/storage/pvc-2222_onemind-db_data-postgres-0/onemind-dumps/app_notes.pgdump';

async function noAxeViolations(container: Element) {
  const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(' | ')}`)).toEqual([]);
}

function status(over: Partial<BackupsStatus> = {}): BackupsStatus {
  return {
    health: 'ok', reason: null, last_success_at: ago(600), last_verified_restore_at: ago(86_400), next_run_at: ago(-1800), copies: 1,
    badges: {
      box: { state: 'unverified', last_success_at: ago(600) },
      system: { state: 'verified', verified_at: ago(86_400), last_success_at: ago(600) },
      apps: { notes: { state: 'verified', verified_at: ago(3 * 86_400), last_success_at: ago(600) }, wiki: { state: 'failing', reason: 'last 3 runs failed' } },
    },
    destinations: [{ id: 'dst_1', kind: 'usb', label: 'Blue disk', primary: true, append_only: false, config: { usb_uuid: '1234-ABCD' }, created_at: ago(9e5) }],
    kit: { state: 'confirmed', issued_at: ago(9e5), confirmed_at: ago(9e5), fingerprint: 'abcd', positions: [3, 9] },
    crash_consistent_apps: ['wiki'], setup: { blocking: [] }, agent: 'ok', ...over,
  };
}

const snap = (id: string, takenAt: string, over: Partial<Snapshot> = {}): Snapshot => ({
  id: id.padEnd(64, '0'), short_id: id.slice(0, 8), unit: 'app:notes', app_id: 'notes', taken_at: takenAt, reason: 'scheduled',
  run_id: 'run_1', paths: [VOL, DUMP], verified_at: null, ...over,
});

describe('backups logic', () => {
  it('words every badge and says how old it is', () => {
    expect(badgeView({ state: 'verified', verified_at: ago(3 * 86_400) }, NOW)).toEqual({ tone: 'ok', label: 'Verified', detail: 'restore tested 3 d ago' });
    expect(badgeView({ state: 'unverified', last_success_at: ago(600) }, NOW)).toMatchObject({ tone: 'warn', detail: 'backed up 10 min ago' });
    expect(badgeView({ state: 'failing' }, NOW)).toMatchObject({ tone: 'bad', label: 'Failing' });
    expect(badgeView(undefined, NOW).label).toBe('No backup');
  });

  it('puts the most urgent notice first', () => {
    expect(overviewNotice(status({ agent: 'unreachable' }))?.tone).toBe('bad');
    expect(overviewNotice(status({ destinations: [] }))?.text).toMatch(/Add a backup destination/);
    expect(overviewNotice(status({ kit: { ...status().kit, state: 'issued' } }))?.text).toMatch(/emergency kit/);
    expect(overviewNotice(status())?.text).toMatch(/One copy only/);
    expect(overviewNotice(status({ copies: 2 }))).toBeNull();
  });

  it('names volumes and builds breadcrumbs from the volume root', () => {
    expect(volumeLabel(VOL)).toBe('data (volume)');
    expect(volumeLabel('/var/lib/rancher/k3s/storage/pvc-2222_onemind-db_data-postgres-0')).toBe('database dump');
    expect(breadcrumbs(`${VOL}/sub/deep`, [VOL]).map((c) => c.label)).toEqual(['data (volume)', 'sub', 'deep']);
    expect(breadcrumbs('/elsewhere', [VOL])).toEqual([{ label: '/', path: '/' }]);
  });

  it('groups restore points by day, newest first, per app', () => {
    const days = snapshotsByDay([snap('a', ago(3600)), snap('b', ago(2 * 86_400)), snap('c', ago(60), { app_id: 'wiki', unit: 'app:wiki' })], 'notes');
    expect(days.map((d) => d.items.map((s) => s.short_id[0]))).toEqual([['a'], ['b']]);
  });

  it('checks the typed-back groups and the restore confirmation', () => {
    expect(typeBackReady([3, 9], { 3: 'abcd', 9: 'WXY2' })).toBe(true);
    expect(typeBackReady([3, 9], { 3: 'abcd' })).toBe(false);
    expect(typeBackReady([3, 9], { 3: 'abc1', 9: 'WXYZ' })).toBe(false); // 1 is not base32
    expect(restoreConfirmed({ app_id: 'notes' }, 'note')).toBe(false);
    expect(restoreConfirmed({ app_id: 'notes' }, ' notes ')).toBe(true);
    expect(restoreConfirmed({ app_id: 'notes', path: `${VOL}/a.txt` }, '')).toBe(true);
    const r = restoreRequest('ab'.repeat(32), { app_id: 'notes' }, 'broke it');
    expect(r.body).toEqual({ snapshot_id: 'ab'.repeat(32), scope: { app_id: 'notes' }, reason: 'broke it' });
    expect(r.curl).toContain('/v1/restores');
    expect(formatBytes(1_234_567)).toBe('1.2 MB');
    expect(formatBytes(null)).toBe('–');
  });
});

describe('BackupsOverview', () => {
  const handlers = { onBackupNow: vi.fn(), onVerifyNow: vi.fn(), onAddDestination: vi.fn(), onRemoveDestination: vi.fn(), onOpenKit: vi.fn(), onOpenRewind: vi.fn() };

  it('shows each app badge in words and files requests from the buttons', async () => {
    const { container } = render(<BackupsOverview status={{ status: 'ready', data: status(), asOf: ago(2) }} runs={[]} now={NOW} isOwner {...handlers} />);
    expect(screen.getByText('notes').closest('li')).toHaveTextContent('Verified· restore tested 3 d ago');
    expect(screen.getByText('wiki').closest('li')).toHaveTextContent('Failing');
    expect(screen.getByText(/copied while running/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Back up now' }));
    expect(handlers.onBackupNow).toHaveBeenCalledOnce();
    await noAxeViolations(container);
  });

  it('pauses requests on stale data and asks for the kit before anything else', async () => {
    render(<BackupsOverview status={{ status: 'ready', data: status({ kit: { ...status().kit, state: 'missing' } }), asOf: ago(600), stale: true }}
      runs={[]} now={NOW} isOwner {...handlers} />);
    expect(screen.getByRole('button', { name: 'Back up now' })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('last known state, not live');
    await userEvent.click(screen.getByRole('button', { name: 'Save the emergency kit' }));
    expect(handlers.onOpenKit).toHaveBeenCalledOnce();
  });

  it('shows errors with their contract code', () => {
    render(<BackupsOverview status={{ status: 'error', code: 'unavailable', message: 'the backup agent is not reachable' }} runs={[]} now={NOW} isOwner={false} {...handlers} />);
    expect(screen.getByText(/unavailable: the backup agent/)).toBeInTheDocument();
  });
});

describe('EmergencyKit', () => {
  const groups = ['AAAA', 'BBBB', 'CCCC', 'DDDD', 'EEEE', 'FFFF', 'GGGG', 'HHHH', 'IIII', 'JJJJ', 'KKKK', 'LLLL', 'MMMM'];
  const issued: KitState = { state: 'issued', issued_at: ago(1), confirmed_at: null, fingerprint: 'f00d', positions: [2, 10] };
  const one: KitOneTime = { owner_key: groups.join('-'), groups, check: 'QQQQ', text: 'kit', qr_payload: 'onemind-kit:v1' };

  it('cannot be skipped: done only after the hub accepts two typed-back groups', async () => {
    const onDone = vi.fn();
    const onConfirm = vi.fn(async (a: Record<string, string>) => {
      if (a['2'] !== 'BBBB' || a['10'] !== 'JJJJ') throw new Error('those groups do not match your kit');
      return { ...issued, state: 'confirmed' as const };
    });
    const { container } = render(
      <EmergencyKit kit={{ ...issued, state: 'missing', positions: [] }} boxName="Home hub" onIssue={async () => ({ kit: issued, one_time: one })}
        onConfirm={onConfirm} onDone={onDone} makeDownload={() => 'blob:kit'} />,
    );
    expect(screen.queryByRole('button', { name: /skip|later|not now/i })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Show my recovery key' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(13);
    expect(screen.getByRole('link', { name: /Download the kit/ })).toHaveAttribute('download', 'home-hub-emergency-kit-2026-11-12.txt');
    expect(screen.getByRole('button', { name: 'Next: prove it' })).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: 'Next: prove it' }));
    expect(screen.queryByText('AAAA')).toBeNull(); // typed from the saved kit, not copied from the screen
    const confirm = screen.getByRole('button', { name: 'Confirm' });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Group 2'), 'bbbb');
    await userEvent.type(screen.getByLabelText('Group 10'), 'XXXX');
    await userEvent.click(confirm);
    expect(await screen.findByRole('alert')).toHaveTextContent('do not match');
    expect(onDone).not.toHaveBeenCalled();
    await userEvent.clear(screen.getByLabelText('Group 10'));
    await userEvent.type(screen.getByLabelText('Group 10'), 'jjjj');
    await userEvent.click(confirm);
    await userEvent.click(await screen.findByRole('button', { name: 'Continue' }));
    expect(onConfirm).toHaveBeenLastCalledWith({ 2: 'BBBB', 10: 'JJJJ' });
    expect(onDone).toHaveBeenCalledOnce();
    await noAxeViolations(container);
  });
});

describe('Restore', () => {
  it('needs the app name typed for a whole-app restore', async () => {
    const onRequest = vi.fn();
    render(<RestoreDialog open snapshot={snap('ab12cd34', ago(7200))} scope={{ app_id: 'notes' }} now={NOW} onClose={() => {}} onRequest={onRequest} showEquivalent />);
    const go = screen.getByRole('button', { name: 'Request restore' });
    expect(go).toBeDisabled();
    expect(screen.getByText(/saved first, as an undo point/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/to confirm/), 'notes');
    await userEvent.click(go);
    expect(onRequest).toHaveBeenCalledWith({ snapshot_id: 'ab12cd34'.padEnd(64, '0'), scope: { app_id: 'notes' } });
  });

  it('puts one file back without stopping the app', async () => {
    const onRequest = vi.fn();
    render(<RestoreDialog open snapshot={snap('ab12cd34', ago(7200))} scope={{ app_id: 'notes', path: `${VOL}/notes.txt` }} now={NOW} onClose={() => {}} onRequest={onRequest} />);
    expect(screen.getByText(/The app keeps running/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Request restore' }));
    expect(onRequest).toHaveBeenCalledOnce();
  });

  it('shows the progress, the health gate and the undo', async () => {
    const onUndo = vi.fn();
    const r: Restore = {
      id: 'rst_1', action_id: 'a1', snapshot_id: 'x', scope: { app_id: 'notes' }, state: 'succeeded',
      plan: { summary: 'Restore notes to yesterday', app_id: 'notes', snapshot: { id: 'x', taken_at: ago(86_400), reason: 'scheduled' }, database: true, steps: [], downtime: '', warnings: [] },
      pre_restore_snapshot_id: 'pre1', health_gate: { verdict: 'pass' },
      steps: [{ at: ago(120), step: 'pre-restore snapshot taken' }, { at: ago(60), step: 'health gate passed' }], created_at: ago(300), finished_at: ago(30), error: null,
    };
    render(<RestoreProgress restore={r} now={NOW} onUndo={onUndo} />);
    expect(screen.getByText('Restored and healthy')).toBeInTheDocument();
    expect(screen.getByText(/Health check on fresh pods: passed/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Undo this restore/ }));
    expect(onUndo).toHaveBeenCalledWith('pre1');
  });
});

describe('Rewind', () => {
  it('browses a restore point and offers download and put-back', async () => {
    const s = snap('ab12cd34', ago(3600), { verified_at: ago(1800) });
    const onOpen = vi.fn();
    const onRestorePath = vi.fn();
    const { rerender, container } = render(
      <Rewind appId="notes" snapshots={{ status: 'ready', data: [s], asOf: ago(1) }} selected={s} entries={null} now={NOW}
        onSelect={() => {}} onOpen={onOpen} fileHref={(x, p) => `/v1/backups/snapshots/${x.id}/file?path=${encodeURIComponent(p)}`}
        onRestoreApp={() => {}} onRestorePath={onRestorePath} />,
    );
    expect(screen.getByText('Restore tested')).toBeInTheDocument();
    expect(screen.getByText(/every folder you open here is recorded/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /data \(volume\)/ }));
    expect(onOpen).toHaveBeenCalledWith(VOL);
    rerender(
      <Rewind appId="notes" snapshots={{ status: 'ready', data: [s], asOf: ago(1) }} selected={s} path={VOL} now={NOW}
        entries={{ status: 'ready', data: [{ name: 'notes.txt', path: `${VOL}/notes.txt`, type: 'file', size: 2 }], asOf: ago(1) }}
        onSelect={() => {}} onOpen={onOpen} fileHref={(x, p) => `/v1/backups/snapshots/${x.id}/file?path=${encodeURIComponent(p)}`}
        onRestoreApp={() => {}} onRestorePath={onRestorePath} />,
    );
    expect(screen.getByRole('link', { name: 'Download' }).getAttribute('href')).toContain('file?path=');
    await userEvent.click(screen.getByRole('button', { name: 'Put notes.txt back' }));
    expect(onRestorePath).toHaveBeenCalledWith(s, `${VOL}/notes.txt`);
    await noAxeViolations(container);
  });
});
