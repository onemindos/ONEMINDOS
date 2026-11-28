// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { NetworkError, OneMindError, PermissionDeniedError } from '@onemind/sdk';
import { ApiError } from '../api/types';
import { viaSdk } from './gateway';

async function caught(e: unknown): Promise<ApiError> {
  try {
    await viaSdk(() => Promise.reject(e));
  } catch (err) {
    return err as ApiError;
  }
  throw new Error('viaSdk did not throw');
}

describe('viaSdk', () => {
  it('keeps "no answer" as the network code, as api/client.ts does', async () => {
    const e = await caught(new NetworkError('could not reach the hub'));
    expect(e).toBeInstanceOf(ApiError);
    expect(e.status).toBe(0);
    expect(e.code).toBe('network');
  });

  it('keeps 401, 403 and the gateway reason', async () => {
    const denied = await caught(new PermissionDeniedError(403, 'permission_denied', 'not allowed to change the password', { reason: 'session_required' }));
    expect(denied.code).toBe('permission_denied');
    expect(denied.reason).toBe('session_required');
    expect((await caught(new OneMindError(401, 'unauthenticated', 'sign in'))).code).toBe('unauthenticated');
    expect((await caught(new OneMindError(409, 'conflict', 'already on'))).code).toBe('unknown');
  });

  it('passes other errors through untouched', async () => {
    const boom = new TypeError('boom');
    expect(await caught(boom)).toBe(boom);
  });
});
