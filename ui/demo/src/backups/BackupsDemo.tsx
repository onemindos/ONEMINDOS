// SPDX-License-Identifier: Apache-2.0
// Demo of ui/src/backups with fixtures in the contract §12.12 shapes (frozen clock).
// Routes: #/backup (overview), #/backup/rewind, #/backup/restore, #/backup/kit.
// `?state=loading|error|stale` shows the overview's other states.
import { useState } from 'react';
import {
  BackupsOverview,
  EmergencyKit,
  RestoreDialog,
  RestoreProgress,
  Rewind,
  useToast,
  type BackupsStatus,
  type KitOneTime,
  type KitState,
  type Load,
  type Restore,
  type Snapshot,
  type TreeEntry,
} from '../../../src';

const NOW = Date.parse('2026-11-12T15:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const VOL = '/var/lib/rancher/k3s/storage/pvc-7d1e_app-paperless_data';
const DUMP = '/var/lib/rancher/k3s/storage/pvc-0c2a_onemind-db_data-postgres-0/onemind-dumps/app_paperless.pgdump';

const status: BackupsStatus = {
  health: 'ok', reason: null, last_success_at: ago(14 * 60), last_verified_restore_at: ago(2 * 86_400), next_run_at: ago(-46 * 60), copies: 2,
  badges: {
    box: { state: 'unverified', last_success_at: ago(14 * 60), reason: 'no passing verified restore within 8 days' },
    system: { state: 'verified', verified_at: ago(2 * 86_400), last_success_at: ago(14 * 60) },
    apps: {
      paperless: { state: 'verified', verified_at: ago(2 * 86_400), last_success_at: ago(14 * 60) },
      'home-assistant': { state: 'unverified', last_success_at: ago(14 * 60) },
      'uptime-kuma': { state: 'failing', reason: 'last verified restore failed', last_success_at: ago(14 * 60) },
    },
  },
  destinations: [
    { id: 'dst_a', kind: 'usb', label: 'Blue USB disk', primary: true, append_only: false, config: { usb_uuid: '6F2A-91C4' }, created_at: ago(40 * 86_400) },
    { id: 'dst_b', kind: 'box', label: 'Garage box', primary: false, append_only: true, config: { url: 'https://garage.local:8000/hub/', user: 'hub' }, created_at: ago(20 * 86_400) },
  ],
  kit: { state: 'confirmed', issued_at: ago(40 * 86_400), confirmed_at: ago(40 * 86_400), fingerprint: '9c1f02ab77e4d310', positions: [4, 11] },
  crash_consistent_apps: ['home-assistant'], setup: { blocking: [] }, agent: 'ok',
};

const runs = [
  { id: 'run_3', action_id: null, reason: 'scheduled', destination_id: 'dst_a', state: 'succeeded' as const, started_at: ago(14 * 60), finished_at: ago(13 * 60), bytes_done: 41_200_000, units: [{ unit: 'system', state: 'succeeded' }, { unit: 'k3s', state: 'succeeded' }, { unit: 'app:paperless', state: 'succeeded' }], error: null },
  { id: 'run_2', action_id: 'a2', reason: 'manual', destination_id: 'dst_a', state: 'partial' as const, started_at: ago(3 * 3600), finished_at: ago(3 * 3600 - 60), bytes_done: 2_100_000, units: [{ unit: 'app:uptime-kuma', state: 'failed', error: 'pre hook sqlite3 failed: database is locked' }], error: null },
];

const snaps: Snapshot[] = [0, 1, 2, 26, 50].map((h, i) => ({
  id: `5e${i}c0ffee`.padEnd(64, 'a'), short_id: `5e${i}c0ffe`, unit: 'app:paperless', app_id: 'paperless', taken_at: ago(h * 3600 + 14 * 60),
  reason: i === 3 ? 'pre-update' : 'scheduled', run_id: `run_${i}`, paths: [VOL, DUMP], verified_at: i === 3 ? ago(2 * 86_400) : null,
}));

const tree: Record<string, TreeEntry[]> = {
  [VOL]: [
    { name: 'media', path: `${VOL}/media`, type: 'dir', size: 0 },
    { name: 'export.json', path: `${VOL}/export.json`, type: 'file', size: 18_340 },
  ],
  [`${VOL}/media`]: [
    { name: 'invoice-2026-10.pdf', path: `${VOL}/media/invoice-2026-10.pdf`, type: 'file', size: 241_100 },
    { name: 'lease.pdf', path: `${VOL}/media/lease.pdf`, type: 'file', size: 1_920_000 },
  ],
};

const restore: Restore = {
  id: 'rst_1', action_id: 'a9', snapshot_id: snaps[1]!.id, scope: { app_id: 'paperless' }, state: 'succeeded',
  plan: { summary: 'Restore paperless to 1 h ago', app_id: 'paperless', snapshot: { id: snaps[1]!.id, taken_at: snaps[1]!.taken_at, reason: 'scheduled' }, database: true, steps: [], downtime: 'the app is stopped during the restore', warnings: [] },
  pre_restore_snapshot_id: 'f00dfeed'.padEnd(64, '0'), health_gate: { verdict: 'pass', checks: 3, fresh_pods: 1 },
  steps: [
    { at: ago(300), step: 'pre-restore snapshot taken' }, { at: ago(280), step: 'stopped paperless' },
    { at: ago(200), step: 'volumes restored' }, { at: ago(190), step: 'database recreated from the snapshot’s dump' },
    { at: ago(185), step: 'started paperless' }, { at: ago(150), step: 'health gate passed' },
  ],
  created_at: ago(400), finished_at: ago(150), error: null,
};

function overviewLoad(): Load<BackupsStatus> {
  const s = new URLSearchParams(window.location.search).get('state');
  if (s === 'loading') return { status: 'loading' };
  if (s === 'error') return { status: 'error', code: 'unavailable', message: 'the backup agent is not reachable' };
  return { status: 'ready', data: s === 'stale' ? { ...status, kit: { ...status.kit, state: 'issued' } } : status, asOf: ago(s === 'stale' ? 600 : 2), stale: s === 'stale' };
}

const GROUPS = ['K7QW', 'M2ZP', 'D4RT', 'X9BN', 'H3LV', 'C6YE', 'P5FJ', 'T8GU', 'W2NK', 'R7SA', 'B3MZ', 'Q6HD', 'L4XC'];

export function BackupsDemo({ arg }: { arg?: string }) {
  const toast = useToast();
  const [selected, setSelected] = useState<Snapshot | undefined>(snaps[1]);
  const [path, setPath] = useState<string | undefined>(VOL);
  const [dialog, setDialog] = useState<{ snapshot: Snapshot; scope: { app_id: string; path?: string } } | null>(
    arg === 'restore' ? { snapshot: snaps[1]!, scope: { app_id: 'paperless' } } : null,
  );
  const requested = () => toast.show({ tone: 'info', title: 'Request sent', body: 'Approve it in Approvals to start.' });

  if (arg === 'kit') {
    const kit: KitState = { state: 'missing', issued_at: null, confirmed_at: null, fingerprint: null, positions: [] };
    const one: KitOneTime = { owner_key: GROUPS.join('-'), groups: GROUPS, check: 'V5TA', text: 'demo kit', qr_payload: 'onemind-kit:v1' };
    return (
      <EmergencyKit
        kit={kit}
        boxName="Home hub"
        onIssue={async () => ({ kit: { state: 'issued', issued_at: ago(1), confirmed_at: null, fingerprint: '9c1f02ab77e4d310', positions: [4, 11] }, one_time: one })}
        onConfirm={async (a) => {
          if (a['4'] !== GROUPS[3] || a['11'] !== GROUPS[10]) throw new Error('those groups do not match your kit; look at the printed key again');
          return { state: 'confirmed', issued_at: ago(1), confirmed_at: ago(0), fingerprint: '9c1f02ab77e4d310', positions: [4, 11] };
        }}
        onDone={() => toast.show({ tone: 'ok', title: 'Setup can continue' })}
        makeDownload={(text) => `data:text/plain;charset=utf-8,${encodeURIComponent(text)}`}
      />
    );
  }

  if (arg === 'rewind' || arg === 'restore') {
    return (
      <>
        <Rewind
          appId="paperless"
          snapshots={{ status: 'ready', data: snaps, asOf: ago(2) }}
          selected={selected}
          path={path}
          entries={path ? { status: 'ready', data: tree[path] ?? [], asOf: ago(2) } : null}
          now={NOW}
          onSelect={(s) => { setSelected(s); setPath(undefined); }}
          onOpen={setPath}
          fileHref={() => '#/backup/rewind'}
          onRestoreApp={(s) => setDialog({ snapshot: s, scope: { app_id: 'paperless' } })}
          onRestorePath={(s, p) => setDialog({ snapshot: s, scope: { app_id: 'paperless', path: p } })}
        />
        <RestoreProgress restore={restore} now={NOW} onUndo={() => setDialog({ snapshot: snaps[0]!, scope: { app_id: 'paperless' } })} />
        {dialog && (
          <RestoreDialog open snapshot={dialog.snapshot} scope={dialog.scope} now={NOW} showEquivalent
            onClose={() => setDialog(null)} onRequest={() => { setDialog(null); requested(); }} />
        )}
      </>
    );
  }

  return (
    <BackupsOverview
      status={overviewLoad()}
      runs={runs}
      now={NOW}
      isOwner
      onBackupNow={requested}
      onVerifyNow={requested}
      onAddDestination={requested}
      onRemoveDestination={requested}
      onOpenKit={() => { window.location.hash = '#/backup/kit'; }}
      onOpenRewind={() => { window.location.hash = '#/backup/rewind'; }}
    />
  );
}
