// SPDX-License-Identifier: Apache-2.0
// One @onemind/sdk client per signed-in token, and the SDK's errors turned into the dashboard's ApiError, so a
// screen that calls the gateway through the generated client reads failures the same way as the rest of the app.
import { useMemo } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { ApiError } from '../api/types';
import { getPasskey } from './webauthn';

/** stepUp: a change the hub wants confirmed with a passkey (D-028) is confirmed in place and sent once more. */
export function useGateway(token: string): OneMind {
  return useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1, stepUp: getPasskey }), [token]);
}

/** Run an SDK call; a OneMindError becomes an ApiError (401, 403 and the gateway's reason are kept). */
export async function viaSdk<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}
