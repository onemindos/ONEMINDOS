// SPDX-License-Identifier: Apache-2.0
import { useMemo } from 'react';
import { OneMind } from '@onemind/sdk';
import { statusRows } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

export function useBoxStatus() {
  const { token, mock } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const status = usePoll(() => mock ? Promise.resolve(null) : sdk.status.get(), 30_000);
  return useMemo(() => statusRows(status.error ? null : status.data ?? null), [status.data, status.error]);
}
