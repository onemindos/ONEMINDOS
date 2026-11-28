// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from 'react';
import { AppState, Linking, Platform } from 'react-native';
import { Sharing, type ResolvedSharePayload, type SharePayload } from '../device/files';
import { badFileName } from '../lib/filesTransfer';
import type { SharedFile } from './shareQueue';

const keyOf = (raw: SharePayload[]) => JSON.stringify(raw.map(p => [p.shareType, p.mimeType, p.value]));
type Incoming = { key: string; files: SharedFile[]; error?: string };
const cannotRead = 'OneMind could not read these attachments. Share the files again from the source app.';

export function canResolve(raw: SharePayload[], android: boolean) {
  return raw.every(p => {
    if (!['file', 'image', 'audio', 'video'].includes(p.shareType)) return false;
    if (!android) return p.value.startsWith('file:');
    try {
      const uri = new URL(p.value);
      return uri.protocol === 'content:' && !!uri.hostname && !/^com\.onemindos\.mobile(?:\.|$)/i.test(uri.hostname);
    } catch {
      return false;
    }
  });
}

export function stagedFiles(raw: SharePayload[], resolved: ResolvedSharePayload[]): SharedFile[] {
  if (keyOf(raw) !== keyOf(resolved)) throw new Error(cannotRead);
  return resolved.map(p => {
    if (!p.contentUri?.startsWith('file:') || !p.originalName || badFileName(p.originalName)) throw new Error(cannotRead);
    return { name: p.originalName, uri: p.contentUri };
  });
}

/** Resolve only native file shares. Compare the complete batch again before clearing Expo's shared cache. */
export function useFileShare() {
  const [incoming, setIncoming] = useState<Incoming>();
  const last = useRef<string | undefined>(undefined);
  const generation = useRef(0);
  useEffect(() => {
    async function refresh() {
      const raw = Sharing.getSharedPayloads();
      const key = keyOf(raw);
      if (key === last.current) return;
      last.current = key;
      const mine = ++generation.current;
      setIncoming(undefined);
      if (!raw.length) return;
      try {
        if (!canResolve(raw, Platform.OS === 'android')) throw new Error('Choose photos or files from the source app.');
        const files = stagedFiles(raw, await Sharing.getResolvedSharedPayloadsAsync());
        if (mine === generation.current) setIncoming({ key, files });
      } catch {
        if (mine === generation.current) setIncoming({ key, files: [], error: cannotRead });
      }
    }
    void refresh();
    const state = AppState.addEventListener('change', s => { if (s === 'active') void refresh(); });
    const link = Linking.addEventListener('url', () => void refresh());
    return () => { generation.current++; last.current = undefined; state.remove(); link.remove(); };
  }, []);
  const clear = (key: string) => {
    if (keyOf(Sharing.getSharedPayloads()) === key) {
      Sharing.clearSharedPayloads();
      last.current = undefined;
      generation.current++;
    }
    setIncoming(current => current?.key === key ? undefined : current);
  };
  return { incoming, clear };
}
