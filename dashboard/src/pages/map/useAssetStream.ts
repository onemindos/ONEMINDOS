// SPDX-License-Identifier: Apache-2.0
// The live asset feed for the Map: GET /v1/events?types=asset.* through @onemind/sdk (#606, #933, #998).
// The gateway first sends the current value of every asset this person may see (data.snapshot), then
// stream.snapshot, then changes, latest-wins per key. Values are gathered in a ref and drawn at most
// every FLUSH_MS, so a snapshot of hundreds of assets is one render, not hundreds.
import { useEffect, useRef, useState } from 'react';
import { OneMindError, type OneMind } from '@onemind/sdk';
import { applyAssetEvent, type AssetValue, type AssetValues } from './model';

export type FeedState = 'off' | 'connecting' | 'live' | 'denied' | 'unavailable';
export const FLUSH_MS = 250;

export function useAssetStream(sdk: OneMind, enabled: boolean): { values: AssetValues; feed: FeedState } {
  const [values, setValues] = useState<AssetValues>(() => new Map());
  const [feed, setFeed] = useState<FeedState>(enabled ? 'connecting' : 'off');
  const store = useRef(new Map<string, AssetValue>());

  useEffect(() => {
    if (!enabled) {
      setFeed('off');
      return;
    }
    const ctrl = new AbortController();
    store.current = new Map();
    let timer: number | undefined;
    const flush = () => {
      timer = undefined;
      if (!ctrl.signal.aborted) setValues(new Map(store.current));
    };
    const later = () => { timer ??= window.setTimeout(flush, FLUSH_MS); };
    setFeed('connecting');
    sdk.events.subscribe({ types: ['asset.*'], signal: ctrl.signal }, (e) => {
      if (e.type === 'stream.snapshot') {
        setFeed('live');
        later();
      } else if (e.type === 'stream.reset') {
        // The gateway dropped this stream (slow client); the next connection sends a fresh snapshot.
        store.current.clear();
        setFeed('connecting');
        later();
      } else if (applyAssetEvent(store.current, e)) {
        later();
      }
    }).catch((err: unknown) => {
      if (ctrl.signal.aborted) return;
      const status = err instanceof OneMindError ? err.status : 0;
      setFeed(status === 401 || status === 403 ? 'denied' : 'unavailable');
    });
    return () => {
      ctrl.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [sdk, enabled]);

  return { values, feed };
}
