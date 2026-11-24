// SPDX-License-Identifier: Apache-2.0
// Home's Storage widget, fed by GET /v1/storage (read-only; owner and admin screens only). Every
// field is checked here and nothing is invented: member capacity is a raw device value, so Home
// shows used data and the disk count, never a "free space" figure.
import { useMemo } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import type { HomeLoadable, StorageStatus } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

/** The widget's shape from the gateway's answer; throws when the answer is not a storage status. */
export function toStorageStatus(raw: unknown, observedAt: string): StorageStatus {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('The hub returned an invalid storage status.');
  const s = raw as Record<string, unknown>;
  if (typeof s.enabled !== 'boolean' || typeof s.available !== 'boolean') throw new Error('The hub returned an invalid storage status.');
  if (!s.enabled || !s.available) return NO_STORAGE(observedAt);
  const used = typeof s.used_bytes === 'number' && Number.isFinite(s.used_bytes) && s.used_bytes >= 0 ? s.used_bytes : null;
  return {
    state: typeof s.state === 'string' && s.state ? s.state : null,
    encrypted: typeof s.encrypted === 'boolean' ? s.encrypted : null,
    used_bytes: used,
    disks: Array.isArray(s.members) ? s.members.length : 0,
    observed_at: observedAt,
  };
}

/** An honest empty answer: demo mode, a disabled service, or nobody allowed to read it. */
export const NO_STORAGE = (observedAt: string): StorageStatus => ({ state: null, encrypted: null, used_bytes: null, disks: 0, observed_at: observedAt });

/** Polls storage every 30 s; `enabled` is false for people who may not read it. */
export function useHomeStorage(enabled: boolean): { value: HomeLoadable<StorageStatus>; reload: () => Promise<void> } {
  const { token, mock } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const p = usePoll(async () => {
    if (mock || !enabled) return NO_STORAGE(new Date().toISOString());
    try {
      return toStorageStatus(await sdk.call<unknown>({ method: 'GET', path: '/v1/storage' }), new Date().toISOString());
    } catch (e) {
      if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
      throw e;
    }
  }, 30_000);
  let value: HomeLoadable<StorageStatus>;
  if (p.data !== undefined) value = { state: 'ready', data: p.data };
  else if (p.error) value = { state: 'error', error: p.error.code, message: p.error.message };
  else value = { state: 'loading' };
  return { value, reload: p.reload };
}
