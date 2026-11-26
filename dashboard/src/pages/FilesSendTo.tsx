// SPDX-License-Identifier: Apache-2.0
// Files > Send to...: hand one file to an app that accepts files. GET /v1/share/targets?type=file lists the switched-on
// apps that accept it and hold the grant; POST /v1/share hands over a reference (the file's place), never its content.
// Only an owner or an adult sends, so the button is not offered to anyone else. The CLI twin is `onemind share`.
import { useRef, useState } from 'react';
import { uuid4 } from '@onemind/sdk';
import { Button, Dialog } from '@onemind/ui';
import type { Entry, FilesApi, FileRoot, ShareResult, ShareTarget } from '../files/api';
import { useSignedIn } from '../session';
import { useRun } from './parts';

export function SendToButton({ api, space, entry }: { api: FilesApi; space: FileRoot; entry: Entry }) {
  const { principal } = useSignedIn();
  const run = useRun();
  const [targets, setTargets] = useState<ShareTarget[]>();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState<ShareResult>();
  const [busy, setBusy] = useState(false);
  const key = useRef<{ sig: string; id: string } | undefined>(undefined);
  if (principal?.role !== 'owner' && principal?.role !== 'adult') return null;
  const start = async () => {
    setDone(undefined);
    const t = await run(() => api.shareTargets('file'), `Could not list apps for ${entry.name}`);
    if (t) { setTargets(t); setOpen(true); }
  };
  const send = async (to: string, verb: 'open' | 'add') => {
    const sig = `${space.root}:${entry.path}|${to}|${verb}`;
    if (key.current?.sig !== sig) key.current = { sig, id: uuid4() };
    setBusy(true);
    const r = await run(() => api.shareSend({ to, verb, object: { type: 'file', ref: `${space.root}:${entry.path}` } }, key.current!.id), `Could not send ${entry.name}`);
    setBusy(false);
    if (r) { setDone(r); key.current = undefined; }
  };
  return (
    <>
      <Button size="sm" variant="secondary" aria-label={`Send ${entry.name} to an app`} onClick={() => void start()}>Send to…</Button>
      <Dialog open={open} onClose={() => setOpen(false)} title={`Send ${entry.name} to an app`} description="The app receives a pointer to this file, not a copy. It can only open it if it already has access to your files."
        actions={<Button variant="ghost" onClick={() => setOpen(false)}>Close</Button>}>
        {done && <p role="status">Sent to {done.to}. It was handed over as “{done.verb}”.</p>}
        {targets && targets.length === 0
          ? <p>No app on this box accepts files yet. Install or switch on an app that handles files, and give it access to your files.</p>
          : <ul aria-label="Apps that accept files">{(targets ?? []).map((t) => <li key={t.app_id}>
            <strong>{t.name}</strong>{' '}
            {t.verbs.map((v) => <Button key={v} size="sm" disabled={busy} onClick={() => void send(t.app_id, v)} aria-label={`${v === 'open' ? 'Open in' : 'Add to'} ${t.name}`}>{v === 'open' ? 'Open in app' : 'Add to app'}</Button>)}
          </li>)}</ul>}
      </Dialog>
    </>
  );
}
