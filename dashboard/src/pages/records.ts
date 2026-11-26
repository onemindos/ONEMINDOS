// SPDX-License-Identifier: Apache-2.0
// Shared by pages whose gateway answers are unconstrained in OpenAPI (`unknown`): every value is
// checked here, never trusted as an invented interface. Paths are typed against the generated spec,
// so a renamed route fails the typecheck.
import { OneMind, OneMindError, type paths } from '@onemind/sdk';
import { ApiError } from '../api/types';

export function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('The hub returned something this page does not understand.');
  return value as Record<string, unknown>;
}
export function records(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) throw new Error('The hub returned something this page does not understand.');
  return value.map(record);
}
export function str(value: unknown, absent = 'Not reported'): string { return typeof value === 'string' && value ? value : absent; }
export function strs(value: unknown): string[] { return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []; }

export type KnownPath = keyof paths;

/** A gateway error in the page's own error type, so `Load` and `usePoll` can say what went wrong. */
export function asApiError(e: unknown): unknown {
  if (e instanceof OneMindError) return new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
  return e;
}
export async function getJson(sdk: OneMind, path: KnownPath | `${KnownPath}?${string}`): Promise<unknown> {
  try { return await sdk.call<unknown>({ method: 'GET', path }); } catch (e) { throw asApiError(e); }
}
