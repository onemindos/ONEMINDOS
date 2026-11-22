// SPDX-License-Identifier: Apache-2.0
// Home's Backups widget, fed by GET /v1/backups/status (served by the gateway; its OpenAPI schema
// is unconstrained, so every field is checked here and nothing is invented). A backup counts as
// "proved" only when the gateway reports a verified restore; until then the widget says so.
import { useMemo } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import type { BackupStatus, HomeLoadable } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll, type Polled } from '../lib/hooks';
import { useSignedIn } from '../session';

const iso = (v: unknown): string | null => (typeof v === 'string' && v && !Number.isNaN(Date.parse(v)) ? v : null);
const label = (d: unknown): string => {
  const r = d && typeof d === 'object' ? (d as Record<string, unknown>) : {};
  return typeof r.label === 'string' && r.label ? r.label : typeof r.kind === 'string' ? r.kind : 'Destination';
};

/** The widget's shape from the gateway's answer; throws when the answer is not a status object. */
export function toBackupStatus(raw: unknown, observedAt: string): BackupStatus {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('The hub returned an invalid backup status.');
  const s = raw as Record<string, unknown>;
  const lastRun = iso(s.last_success_at);
  const state = s.health === 'ok' ? 'ok' : s.health === 'failing' ? 'failing' : 'behind';
  const dests = Array.isArray(s.destinations) ? s.destinations : [];
  return {
    last_run: lastRun,
    last_verified_restore: iso(s.last_verified_restore_at),
    // The gateway reports health for the box, not per destination: each destination carries it.
    destinations: dests.map((d) => ({ name: label(d), last_success: lastRun, state })),
    observed_at: observedAt,
  };
}

/** An empty, honest answer for demo mode: there is no backup data to show. */
export const NO_BACKUPS = (observedAt: string): BackupStatus => ({ last_run: null, last_verified_restore: null, destinations: [], observed_at: observedAt });

export interface HomeBackups {
  value: HomeLoadable<BackupStatus>;
  reload: () => Promise<void>;
}

/** Polls the backup status every 30 s; `enabled` is false for people who may not read it. */
export function useHomeBackups(enabled: boolean): HomeBackups {
  const { token, mock } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const p: Polled<BackupStatus> = usePoll(async () => {
    if (mock || !enabled) return NO_BACKUPS(new Date().toISOString());
    try {
      return toBackupStatus(await sdk.call<unknown>({ method: 'GET', path: '/v1/backups/status' }), new Date().toISOString());
    } catch (e) {
      if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
      throw e;
    }
  }, 30_000);
  let value: HomeLoadable<BackupStatus>;
  if (p.data !== undefined) value = { state: 'ready', data: p.data };
  else if (p.error) value = { state: 'error', error: p.error.code, message: p.error.message };
  else value = { state: 'loading' };
  return { value, reload: p.reload };
}
