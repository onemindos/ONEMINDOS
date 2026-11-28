// SPDX-License-Identifier: Apache-2.0
// The asset values for the Map tab: one `GET /v1/events?types=asset.*` stream through the gateway (never NATS), kept in
// memory. When the connection drops the last map stays on screen and every label keeps counting its age.
// The gateway does not replay removals on reconnect (eventstream.py), so each new connection's snapshot is collected
// into a fresh map and swapped in when `stream.snapshot` arrives: an asset removed meanwhile disappears.
import { useEffect, useState } from 'react';
import { AppState } from 'react-native';
import { OP } from '../api/client';
import type { HubEvent } from '../api/types';
import { useSignedIn } from '../session';
import { EventStream, type StreamState } from './events';
import { applyAssetEvent, type AssetMap } from './map';

export interface AssetFeed {
  assets: AssetMap;
  state: StreamState | 'off';
  /** The current connection's snapshot arrived, so an empty map can mean "no assets" (see `store`). */
  ready: boolean;
  /** The gateway's asset store (`stream.snapshot` data.state): only `ready` means an empty map is really empty. */
  store?: string;
  /** The snapshot's count differs from the values received: the map may be missing some. */
  incomplete: boolean;
}

export function useAssets(): AssetFeed {
  const { api, features } = useSignedIn();
  const [feed, setFeed] = useState<AssetFeed>({ assets: {}, state: 'off', ready: false, incomplete: false });

  useEffect(() => {
    const ep = features.has(OP.events) ? api.eventsEndpoint() : undefined;
    if (!ep) {
      setFeed((f) => ({ ...f, state: 'off' }));
      return;
    }
    let live: AssetMap = {};
    let incoming: AssetMap | undefined; // this connection's snapshot while it arrives
    let received = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const flush = () => {
      timer = undefined;
      setFeed((f) => ({ ...f, assets: live }));
    };
    const stream = new EventStream({
      url: ep.url,
      bearer: ep.bearer,
      refresh: ep.refresh,
      types: ['asset.*'],
      onEvent: (e: HubEvent) => {
        if (e.type === 'stream.snapshot') {
          const d = (e.data ?? {}) as { count?: unknown; state?: unknown };
          const complete = typeof d.count !== 'number' || d.count === received;
          live = incoming ?? {};
          incoming = undefined;
          received = 0;
          if (timer !== undefined) clearTimeout(timer);
          timer = undefined;
          setFeed((f) => ({ ...f, assets: live, ready: true, store: typeof d.state === 'string' ? d.state : undefined, incomplete: !complete }));
          return;
        }
        if (e.type === 'asset.value' && e.data?.snapshot === true) {
          if (!incoming) {
            incoming = {};
            received = 0;
          }
          received++;
          incoming = applyAssetEvent(incoming, e);
          return;
        }
        const next = applyAssetEvent(live, e);
        if (next === live) return;
        live = next;
        if (timer === undefined) timer = setTimeout(flush, 250); // a burst of values is one render
      },
      onState: (st) => {
        if (st !== 'open') incoming = undefined; // a half-received snapshot is dropped
        setFeed((f) => ({ ...f, state: st }));
      },
    });
    if (AppState.currentState !== 'background') stream.start();
    const sub = AppState.addEventListener('change', (s) => (s === 'active' ? stream.start() : stream.stop()));
    return () => {
      sub.remove();
      stream.stop();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [api, features]);

  return feed;
}
