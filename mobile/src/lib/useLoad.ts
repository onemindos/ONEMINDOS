// SPDX-License-Identifier: Apache-2.0
// One read from the hub for a screen: loading, data, or an ApiError. A 403 is its own flag so an owner-only
// screen can say so plainly instead of showing an error.
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/types';

export interface Loaded<T> {
  data?: T;
  error?: ApiError;
  loading: boolean;
  forbidden: boolean;
  reload(): Promise<void>;
}

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): Loaded<T> {
  const [state, setState] = useState<{ data?: T; error?: ApiError; loading: boolean }>({ loading: true });
  const seq = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps);
  const reload = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const data = await run();
      if (mine === seq.current) setState({ data, loading: false });
    } catch (e) {
      if (mine === seq.current) setState((s) => ({ data: s.data, error: e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e)), loading: false }));
    }
  }, [run]);
  useEffect(() => {
    void reload();
    return () => {
      seq.current++;
    };
  }, [reload]);
  return { ...state, forbidden: state.error?.code === 'permission_denied', reload };
}
