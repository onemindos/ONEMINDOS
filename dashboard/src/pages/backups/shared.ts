// SPDX-License-Identifier: Apache-2.0
// Shared by the Backups page and its two forms. Backup reads are unconstrained in OpenAPI
// (`unknown`), so every value is validated here instead of trusting an invented interface.
import { useRef, useState } from 'react';
import { OneMind, OneMindError, uuid4, type paths } from '@onemind/sdk';
import { ApiError } from '../../api/types';

export function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('The hub returned an invalid backup record.');
  return value as Record<string, unknown>;
}
export function rows(value: unknown) {
  if (!Array.isArray(value)) throw new Error('The hub returned an invalid backup list.');
  return value.map(object);
}
export function text(value: unknown, absent = 'Not reported') { return typeof value === 'string' && value ? value : absent; }
export function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []; }

/** Paths are typed against the generated OpenAPI, so a renamed route fails the typecheck. */
export type BackupPath = keyof paths;
export async function read(sdk: OneMind, path: BackupPath | `${BackupPath}?${string}`) {
  try { return await sdk.call<unknown>({ method: 'GET', path }); }
  catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}

const ACTION_STATES = ['requested', 'awaiting_approval', 'accepted', 'dispatched', 'succeeded', 'failed', 'cancelled', 'expired', 'outcome_unknown'];
export interface Filed { id: string; state: string; body: Record<string, unknown> }

/**
 * File one change as an approval request (never an approval): `approve` is always false. One
 * idempotency key and one expiry live as long as the form body is unchanged, so a lost reply is
 * retried as the same request and can never become two. The body (which may hold credentials) lives
 * in memory only and is dropped on success.
 */
export function useFiling(sdk: OneMind, token: string) {
  const sending = useRef(false);
  const pending = useRef<{ key: string; sig: string; expires: string } | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const file = async (path: BackupPath, type: string, fields: Record<string, unknown>): Promise<Filed | undefined> => {
    if (sending.current) return undefined;
    sending.current = true; setBusy(true); setError('');
    const sig = path + JSON.stringify(fields);
    if (pending.current?.sig !== sig) pending.current = { key: uuid4(), sig, expires: new Date(sdk.hubNow() + 24 * 60 * 60 * 1000).toISOString() };
    const p = pending.current;
    const body = { ...fields, approve: false, expires_at: p.expires };
    const client = new OneMind({ baseUrl: sdk.baseUrl, token, retries: 1, fetch: (url, init) => {
      const headers = new Headers(init?.headers);
      headers.set('Idempotency-Key', p.key);
      return fetch(url, { ...init, headers });
    } });
    try {
      const reply = object(await client.call<unknown>({ method: 'POST', path, body }));
      if (typeof reply.id !== 'string' || !reply.id.trim() || reply.type !== type || reply.idempotency_key !== p.key
        || typeof reply.state !== 'string' || !ACTION_STATES.includes(reply.state)) throw new Error('The hub returned an incomplete or mismatched request reply');
      pending.current = undefined;
      return { id: reply.id, state: reply.state, body: reply };
    } catch (e) {
      if (e instanceof OneMindError && e.status === 409 && e.code === 'expired') pending.current = undefined;
      const why = e instanceof OneMindError && e.status === 403 ? 'Only the owner can file this.' : e instanceof Error ? e.message : String(e);
      setError(`${why}. Retry the same request; it may already have been filed.`);
      return undefined;
    } finally { sending.current = false; setBusy(false); }
  };
  return { file, busy, error };
}
