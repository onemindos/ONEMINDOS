import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/types';
import { useSession } from '../session';

/** A clock that ticks every `ms`, so "last seen Ns ago" keeps counting up. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}

export interface Polled<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  /** When the data currently on screen was fetched (ms since epoch). */
  fetchedAt: number | undefined;
  reload: () => Promise<void>;
}

/**
 * Fetch now and every `intervalMs` (heartbeats arrive every 10 s, §1).
 * On error the previous data is KEPT but `error` is set, so screens can say
 * "could not refresh, showing data from N s ago" instead of pretending.
 * A 401 signs the user out.
 */
export function usePoll<T>(fn: () => Promise<T>, intervalMs = 10_000): Polled<T> {
  const { signOut } = useSession();
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError>();
  const [loading, setLoading] = useState(true);
  const [fetchedAt, setFetchedAt] = useState<number>();
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const alive = useRef(true);
  // Requests can overlap (interval plus a manual reload) and land out of order.
  // Only a response newer than the last one applied may replace the data.
  const sent = useRef(0);
  const applied = useRef(0);

  const reload = useCallback(async () => {
    const seq = ++sent.current;
    try {
      const d = await fnRef.current();
      if (!alive.current || seq < applied.current) return;
      applied.current = seq;
      setData(d);
      setError(undefined);
      setFetchedAt(Date.now());
    } catch (e) {
      if (!alive.current || seq < applied.current) return;
      const err = e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e));
      if (err.code === 'unauthenticated') signOut();
      setError(err);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [signOut]);

  useEffect(() => {
    alive.current = true;
    void reload();
    const id = intervalMs > 0 ? window.setInterval(() => void reload(), intervalMs) : undefined;
    return () => {
      alive.current = false;
      if (id !== undefined) window.clearInterval(id);
    };
  }, [reload, intervalMs]);

  return { data, error, loading, fetchedAt, reload };
}
