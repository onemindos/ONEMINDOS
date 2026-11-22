// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react';
import { useSignedIn } from '../session';
import { useLoad } from '../lib/useLoad';
import { Button, H1, Loading, Notice, P, Screen } from '../ui/bits';
import { join } from '../screens/FilesScreen';
import type { Destination } from './shareQueue';

type Folder = Destination & { name: string };

export function ShareDestination({ names, send, cancel, busy, error }: {
  names: string[]; send: (to: Destination) => void; cancel(): void; busy: boolean; error?: string;
}) {
  const { api, label } = useSignedIn();
  const roots = useLoad(() => api.filesRoots(), [api]);
  const [trail, setTrail] = useState<Folder[]>([]);
  const at = trail[trail.length - 1];
  const writable = roots.data?.filter(r => r.writable) ?? [];
  return <Screen>
    <H1>Send to OneMind</H1>
    <P>{names.join('\n')}</P>
    <P>Choose a folder on {label}.</P>
    {error && <Notice tone="bad" text={error} />}
    {roots.loading ? <Loading what="folders" /> : roots.error ? <Notice tone="bad" text="Could not read your folders." /> :
      at && writable.some(r => r.root === at.root) ?
        <FolderView key={JSON.stringify(at)} at={at} busy={busy} enter={name => setTrail([...trail, { ...at, path: join(at.path, name) }])}
          back={() => setTrail(trail.slice(0, -1))} send={() => send({ root: at.root, path: at.path })} /> :
        writable.length ? writable.map(r => <Button key={r.root} label={r.name} disabled={busy} onPress={() => setTrail([{ root: r.root, name: r.name, path: r.path || '/' }])} />) :
          <P>You have no writable folders on this hub.</P>}
    <Button label="Cancel" variant="secondary" disabled={busy} onPress={cancel} />
  </Screen>;
}

function FolderView({ at, busy, enter, back, send }: {
  at: Folder; busy: boolean; enter(name: string): void; back(): void; send(): void;
}) {
  const { api } = useSignedIn();
  const folder = useLoad(() => api.filesList(at.root, at.path), [api, at.root, at.path]);
  return <>
    <P>{at.name} {at.path}</P>
    {folder.loading ? <Loading what="folder" /> : folder.error ? <Notice tone="bad" text="Could not open this folder." /> : <>
      {(folder.data ?? []).filter(f => f.type === 'dir').map(f => <Button key={f.name} label={f.name} disabled={busy} onPress={() => enter(f.name)} />)}
      <Button label={busy ? 'Preparing files…' : 'Send to this folder'} disabled={busy} onPress={send} />
    </>}
    <Button label="Back" variant="secondary" disabled={busy} onPress={back} />
  </>;
}
