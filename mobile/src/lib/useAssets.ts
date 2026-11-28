// SPDX-License-Identifier: Apache-2.0
// The asset values for the Map tab: one `GET /v1/events?types=asset.*` stream through the gateway (never NATS), kept in
// memory. When the connection drops the last map stays on screen and every label keeps counting its age.
import { useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { OP } from '../api/client';
import { useSignedIn } from '../session';
import { EventStream, type StreamState } from './events';
import { applyAssetEvent, type AssetMap } from './map';

export interface AssetFeed {
  assets: AssetMap;
  state: StreamState | 'off';
  /** The stream finished its snapshot (stream.snapshot), so an empty map really means no assets. */
  ready: boolean;
}

export function useAssets(): AssetFeed {
  const { api, features } = useSignedIn();
  const [assets, setAssets] = useState<AssetMap>({});
  const [state, setState] = useState<StreamState | 'off'>('off');
  const [ready, setReady] = useState(false);
  const live = useRef<AssetMap>({});

  useEffect(() => {
    const ep = features.has(OP.events) ? api.eventsEndpoint() : undefined;
    if (!ep) {
      setState('off');
      return;
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    const flush = () => {
      timer = undefined;
      setAssets(live.current);
    };
    const stream = new EventStream({
      url: ep.url,
      bearer: ep.bearer,
      refresh: ep.refresh,
      types: ['asset.*'],
      onEvent: (e) => {
        if (e.type === 'stream.snapshot') {
          setReady(true);
          return;
        }
        const next = applyAssetEvent(live.current, e);
        if (next === live.current) return;
        live.current = next;
        if (timer === undefined) timer = setTimeout(flush, 250); // a burst of values is one render
      },
      onState: setState,
    });
    if (AppState.currentState !== 'background') stream.start();
    const sub = AppState.addEventListener('change', (s) => (s === 'active' ? stream.start() : stream.stop()));
    return () => {
      sub.remove();
      stream.stop();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [api, features]);

  return { assets, state, ready };
}
