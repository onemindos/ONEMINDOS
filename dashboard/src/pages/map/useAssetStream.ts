// SPDX-License-Identifier: Apache-2.0
// The live asset feed for the Map: GET /v1/events?types=asset.* through @onemind/sdk (#606, #933, #998).
// Per connection the gateway sends the current value of every asset this person may see (data.snapshot true),
// then stream.snapshot {count, state}, then changes, latest-wins per key (core eventstream.py).
//
// Asset events carry no SSE id, so when the SDK reconnects by itself there is no replay: the new connection
// sends a whole new snapshot, and a key removed while we were away simply is not in it. So snapshot values are
// gathered into a fresh map and swapped in only at stream.snapshot; until then the last complete map stays on
// screen (marked "Reconnecting…"), and nothing is wiped early. Changes after the snapshot apply to the shown map.
// Values are drawn at most every FLUSH_MS, so a snapshot of hundreds of assets is one render.
import { useEffect, useState } from 'react';
import { NetworkError, OneMindError, errorFor, type OneMind } from '@onemind/sdk';
import { applyAssetEvent, type AssetValue, type AssetValues } from './model';

/** The connection: demo (off), first connect, a complete snapshot received (live), between connections, refused. */
export type FeedState = 'off' | 'connecting' | 'live' | 'reconnecting' | 'denied' | 'unavailable';
/** The hub's own asset state from stream.snapshot (core fanout.py AssetState.state); undefined before one. */
export type AssetsState = 'off' | 'pending' | 'error' | 'ready';
export const FLUSH_MS = 250;

export interface AssetStream { values: AssetValues; feed: FeedState; assets?: AssetsState }

const ASSET_STATES: ReadonlySet<string> = new Set(['off', 'pending', 'error', 'ready']);

export function useAssetStream(sdk: OneMind, enabled: boolean): AssetStream {
  const [values, setValues] = useState<AssetValues>(() => new Map());
  const [feed, setFeed] = useState<FeedState>(enabled ? 'connecting' : 'off');
  const [assets, setAssets] = useState<AssetsState>();

  useEffect(() => {
    if (!enabled) {
      setFeed('off');
      return;
    }
    const ctrl = new AbortController();
    let shown = new Map<string, AssetValue>();    // the last complete snapshot plus the changes since
    let incoming = new Map<string, AssetValue>(); // the snapshot of the current connection, still arriving
    let complete = false;                         // a stream.snapshot has been seen on some connection
    let timer: number | undefined;
    const flush = () => {
      timer = undefined;
      if (!ctrl.signal.aborted) setValues(new Map(shown));
    };
    const later = () => { timer ??= window.setTimeout(flush, FLUSH_MS); };
    setFeed('connecting');
    setAssets(undefined);

    // The SDK's own reader, plus one signal: when a connection ends (the SDK then backs off and reconnects).
    async function* transport(url: string, headers: Record<string, string>, signal: AbortSignal): AsyncIterable<string> {
      incoming = new Map();
      try {
        let res: Response;
        try {
          res = await fetch(url, { headers, signal });
        } catch {
          throw new NetworkError('could not reach the hub');
        }
        if (!res.ok) {
          const b = (await res.json().catch(() => undefined)) as { error?: string; message?: string } | undefined;
          throw errorFor(res.status, b?.error ?? (res.status === 404 ? 'not_found' : 'unexpected_response'), b?.message ?? `HTTP ${res.status}`);
        }
        if (!res.body) throw new NetworkError('no streaming body');
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        for (;;) {
          let chunk: ReadableStreamReadResult<Uint8Array>;
          try {
            chunk = await reader.read();
          } catch {
            throw new NetworkError('event stream closed');
          }
          if (chunk.done) return;
          yield dec.decode(chunk.value, { stream: true });
        }
      } finally {
        if (!ctrl.signal.aborted) setFeed(complete ? 'reconnecting' : 'connecting');
      }
    }

    sdk.events.subscribe({ types: ['asset.*'], signal: ctrl.signal, transport }, (e) => {
      if (e.type === 'stream.snapshot') {
        shown = incoming;
        incoming = new Map();
        complete = true;
        const st = e.data?.state;
        setAssets(typeof st === 'string' && ASSET_STATES.has(st) ? (st as AssetsState) : undefined);
        setFeed('live');
        later();
      } else if (e.type === 'stream.reset') {
        // The gateway is dropping this connection (slow client). Keep the last map; the next snapshot replaces it.
        incoming = new Map();
      } else if (e.data?.snapshot === true) {
        applyAssetEvent(incoming, e);
      } else if (applyAssetEvent(shown, e)) {
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

  return { values, feed, assets };
}
