// SPDX-License-Identifier: Apache-2.0
// Home's backups, updates and mesh widgets, read from the real gateway routes:
// GET /v1/backups/status, GET /v1/os/updates and GET /v1/mesh. Their OpenAPI responses are
// unconstrained, so each mapper checks the shape and throws instead of inventing a value.
import { useMemo } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import type { BackupStatus, HomeApp, HomeLoadable, MeshStatus, UpdatesStatus } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll, type Polled } from '../lib/hooks';
import { useSignedIn } from '../session';

type Rec = Record<string, unknown>;
function rec(v: unknown, what: string): Rec {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error(`The hub returned an invalid ${what}.`);
  return v as Rec;
}
const str = (v: unknown) => (typeof v === 'string' && v ? v : null);

export function backupsFromStatus(raw: unknown, observedAt: string): BackupStatus {
  const s = rec(raw, 'backup status');
  if (typeof s.health !== 'string') throw new Error('The hub returned an invalid backup status.');
  if (s.health === 'failing') throw new Error(str(s.reason) ?? 'Backups are failing.');
  return { last_run: str(s.last_success_at), last_verified_restore: str(s.last_verified_restore_at), destinations: [], observed_at: observedAt };
}

type OsUpdates = Pick<UpdatesStatus, 'os' | 'checked_at'>;

/** Validates the hub's OS update payload. Throws on a bad shape, so call it inside the poll fn. */
export function osUpdatesFromHub(rawOs: unknown, observedAt: string): OsUpdates {
  const s = rec(rawOs, 'update status');
  if (!Array.isArray(s.nodes)) throw new Error('The hub returned an invalid update status.');
  const nodes = s.nodes.map((n) => rec(n, 'update status'));
  const offer = nodes.find((n) => str(n.available_version));
  const checks = nodes.map((n) => str(n.last_check)).filter((x): x is string => !!x).sort();
  return {
    os: offer ? { from: str(offer.current_version) ?? 'current', to: str(offer.available_version)!, channel: offer.channel === 'security' ? 'security' : 'stable' } : null,
    checked_at: checks.length ? checks[checks.length - 1]! : observedAt,
  };
}

/** Pure, non-throwing: adds the app updates from the apps list to the validated OS part. */
export function withAppUpdates(os: OsUpdates, apps: HomeApp[] | undefined): UpdatesStatus {
  return { ...os, apps: (apps ?? []).filter((a) => a.update_available).map((a) => ({ app_id: a.id, from: a.version, to: a.update_available! })) };
}

export function updatesFromHub(rawOs: unknown, apps: HomeApp[] | undefined, observedAt: string): UpdatesStatus {
  return withAppUpdates(osUpdatesFromHub(rawOs, observedAt), apps);
}

export function meshFromHub(raw: unknown, observedAt: string): MeshStatus {
  const m = rec(raw, 'network view');
  if (!Array.isArray(m.nodes)) throw new Error('The hub returned an invalid network view.');
  const control = m.control && typeof m.control === 'object' ? (m.control as Rec).state : undefined;
  return {
    links: m.nodes.map((n) => {
      const x = rec(n, 'network view');
      const state = x.state === 'up' || x.state === 'down' ? x.state : 'degraded';
      return { hostname: str(x.name) ?? str(x.node_id) ?? 'node', via: 'mesh' as const, state };
    }),
    remote_access: control === 'up' ? 'mesh' : 'off',
    observed_at: observedAt,
  };
}

function toLoadable<T>(p: Polled<T>): HomeLoadable<T> {
  if (p.data !== undefined) return { state: 'ready', data: p.data };
  if (p.error) return { state: 'error', error: p.error.code, message: p.error.message };
  return { state: 'loading' };
}

async function get(sdk: OneMind, path: string): Promise<unknown> {
  try {
    return await sdk.call<unknown>({ method: 'GET', path });
  } catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}

const DEMO = (what: string): HomeLoadable<never> => ({ state: 'error', error: 'not_available', message: `Connect to a real hub to see ${what}. Demo mode has none.` });

/** The three widget feeds. In demo mode nothing is fetched and each says so. */
export function useHomeExtras(apps: HomeApp[] | undefined, observedAt: string) {
  const { token, mock } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const interval = mock ? 0 : 30_000;
  const backups = usePoll(async () => (mock ? (undefined as never) : backupsFromStatus(await get(sdk, '/v1/backups/status'), observedAt)), interval);
  const os = usePoll(async () => (mock ? (undefined as never) : osUpdatesFromHub(await get(sdk, '/v1/os/updates'), observedAt)), interval);
  const mesh = usePoll(async () => (mock ? (undefined as never) : meshFromHub(await get(sdk, '/v1/mesh'), observedAt)), interval);
  if (mock) return { backups: DEMO('backups'), updates: DEMO('updates'), mesh: DEMO('network links') };
  const updates: HomeLoadable<UpdatesStatus> = os.data !== undefined ? { state: 'ready', data: withAppUpdates(os.data, apps) } : toLoadable(os as unknown as Polled<UpdatesStatus>);
  return { backups: toLoadable(backups), updates, mesh: toLoadable(mesh) };
}
