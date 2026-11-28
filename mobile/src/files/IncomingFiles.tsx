// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from 'react';
import { Modal } from 'react-native';
import type { Directory } from '../device/files';
import { OP } from '../api/client';
import { useSignedIn } from '../session';
import { uploadProblem } from '../lib/filesTransfer';
import { Button, H1, Notice, P, Screen } from '../ui/bits';
import { useFileShare } from './incoming';
import { ShareDestination } from './ShareDestination';
import { deliverShare, discardShare, readShare, shareDirectory, stageShare, type Destination, type ShareJob } from './shareQueue';
import { scheduleShare, unscheduleShare } from './shareBackground';

export function IncomingFiles() {
  const { connection, principal } = useSignedIn();
  return connection.mode === 'live' && principal?.kind === 'person' ?
    <Inbox key={JSON.stringify([connection.hubUrl, principal.id])} hub={connection.hubUrl} person={principal.id} /> : null;
}

function Inbox({ hub, person }: { hub: string; person: string }) {
  const { api, features } = useSignedIn();
  const { incoming, clear } = useFileShare();
  const [dir, setDir] = useState<Directory>();
  const [job, setJob] = useState<ShareJob>();
  const [message, setMessage] = useState<string>();
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);

  useEffect(() => {
    let here = true;
    void (async () => {
      const directory = await shareDirectory(hub, person);
      const waiting = await readShare(directory);
      if (here) { setJob(waiting); setMessage(waiting?.error); setDir(directory); }
    })().catch(() => { if (here) setMessage('Could not open the share inbox on this phone.'); });
    return () => { here = false; };
  }, [hub, person]);

  async function send(destination?: Destination) {
    if (lock.current || !dir) return;
    lock.current = true;
    setBusy(true);
    setMessage(undefined);
    try {
      if (destination && incoming) {
        const staged = await stageShare(dir, incoming.files, destination);
        setJob(staged);
        clear(incoming.key);
      }
      await scheduleShare().catch(() => undefined); // if OS scheduling is restricted, the foreground transfer still runs
      await deliverShare(api, dir, true);
      setJob(undefined);
      setMessage('The files are in your chosen folder.');
      await unscheduleShare().catch(() => undefined);
    } catch (e) {
      setMessage(uploadProblem(e));
    } finally { lock.current = false; setBusy(false); }
  }

  function close() {
    if (lock.current) return;
    if (!job && incoming) clear(incoming.key);
    setMessage(undefined);
    if (job && dir) {
      try { discardShare(dir); setJob(undefined); }
      catch (e) { setMessage(uploadProblem(e)); }
    }
  }

  if (!incoming && !job && !message) return null;
  const canSend = features.has(OP.filesUploads) && features.has(OP.filesRoots) && features.has(OP.filesList);
  return <Modal visible onRequestClose={() => { if (!job) close(); }} presentationStyle="pageSheet">
    {dir && !job && incoming && !incoming.error && canSend ?
      <ShareDestination key={incoming.key} names={incoming.files.map(f => f.name)} busy={busy} error={message} cancel={close} send={to => void send(to)} /> :
      <Screen><H1>Send to OneMind</H1>
        {job && <P>{job.files.join('\n')}{'\n'}{job.destination.root} {job.destination.path}</P>}
        {message ? <Notice text={message} tone={job ? 'warn' : 'info'} /> : <P>{job ? (busy ? 'Sending files…' : 'These files are queued for delivery.') :
          incoming?.error ?? (!canSend ? 'This hub does not offer Files uploads for this sign-in.' : 'Opening your share inbox…')}</P>}
        {job && !busy && <Button label="Resume sending" onPress={() => void send()} />}
        <Button label={job ? 'Discard remaining files' : 'Done'} variant="secondary" disabled={busy} onPress={close} />
      </Screen>}
  </Modal>;
}
