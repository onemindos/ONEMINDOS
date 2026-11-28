// SPDX-License-Identifier: Apache-2.0
// Files > Send to...: hand one file to an app that accepts files. GET /v1/share/targets?type=file lists the switched-on
// apps that accept it and hold the grant; POST /v1/share hands over a reference (the file's place), never its content.
// Only an owner or an adult sends, so the button is not offered to anyone else. The CLI twin is `onemind share`.
import { useRef, useState } from 'react';
import { uuid4 } from '@onemind/sdk';
import { Button, Dialog } from '@onemind/ui';
import type { Entry, FilesApi, FileRoot, ShareResult, ShareTarget } from '../files/api';
import { useShell } from '../shell/Shell';
import { useRun } from './parts';

export function SendToButton({ api, space, entry }: { api: FilesApi; space: FileRoot; entry: Entry }) {
  // The signed-in role as the Files page reads it (#1321): known once the hub answers who this is.
  const { role } = useShell();
  const run = useRun();
  const [targets, setTargets] = useState<ShareTarget[]>();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState<{ result: ShareResult; name: string }>();
  const [busy, setBusy] = useState(false);
  // Set while a send failed or its reply was lost: pressing the same button again reuses the key, so the
  // gateway replays that first share instead of sending a second one.
  const [retrying, setRetrying] = useState<string>();
  const key = useRef<{ sig: string; id: string } | undefined>(undefined);
  if (role !== 'owner' && role !== 'adult') return null;
  const start = async () => {
    setDone(undefined);
    setRetrying(undefined);
    key.current = undefined;
    const t = await run(() => api.shareTargets('file'), `Could not list apps for ${entry.name}`);
    if (t) { setTargets(t); setOpen(true); }
  };
  const send = async (t: ShareTarget, verb: 'open' | 'add') => {
    const sig = `${space.root}:${entry.path}|${t.app_id}|${verb}`;
    if (key.current?.sig !== sig) key.current = { sig, id: uuid4() };
    setBusy(true);
    setDone(undefined);
    const r = await run(() => api.shareSend({ to: t.app_id, verb, object: { type: 'file', ref: `${space.root}:${entry.path}` } }, key.current!.id), `Could not send ${entry.name}`);
    setBusy(false);
    if (r) { setDone({ result: r, name: t.name }); setRetrying(undefined); key.current = undefined; } else setRetrying(sig);
  };
  const label = (t: ShareTarget, v: 'open' | 'add') => `${v === 'open' ? 'Open in' : 'Add to'} ${t.name}`;
  return (
    <>
      <Button size="sm" variant="secondary" aria-label={`Send ${entry.name} to an app`} onClick={() => void start()}>Send to…</Button>
      <Dialog open={open} onClose={() => setOpen(false)} title={`Send ${entry.name} to an app`} description="The app receives a pointer to this file, not a copy. It can only open it if it already has access to your files."
        actions={<Button variant="ghost" onClick={() => setOpen(false)}>Close</Button>}>
        {done && <p role="status">Sent to {done.name}. {done.result.verb === 'add' ? `${entry.name} was added to ${done.name}.` : `${done.name} can now open ${entry.name}.`} Pressing a button again sends it again.</p>}
        {retrying && <p role="status" className="om-hint">Not sent yet. Pressing the same button again retries this one share; the app still gets it only once.</p>}
        {targets && targets.length === 0
          ? <p>No app on this box accepts files yet. Install or switch on an app that handles files, and give it access to your files.</p>
          : <ul aria-label="Apps that accept files">{(targets ?? []).map((t) => <li key={t.app_id}>
            <strong>{t.name}</strong>{' '}
            {t.verbs.map((v) => <Button key={v} size="sm" disabled={busy} onClick={() => void send(t, v)} aria-label={label(t, v)}>{v === 'open' ? 'Open in app' : 'Add to app'}</Button>)}
          </li>)}</ul>}
      </Dialog>
    </>
  );
}
