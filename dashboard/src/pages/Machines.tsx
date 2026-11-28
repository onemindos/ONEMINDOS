// SPDX-License-Identifier: Apache-2.0
// Machines (MACH-01, #281): the virtual machines on this box, from GET /v1/machines, and whether the
// box can run them at all, from GET /v1/machines/capabilities. Create, start, stop and remove are
// only ever REQUESTS (POST /v1/actions, machine.*): they wait in Approvals and nothing reaches the
// runtime until an owner approves (create, start, stop, restart, force off, snapshot, clone, remove). States are the gateway's own words (creating, stopped, running,
// unknown); the screen never guesses a better one.
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, type components, type paths } from '@onemind/sdk';
import { MachineCreateForm } from './MachineCreateForm';
import { Button, Card, Dialog, EmptyState, PageHeader, StatusPill, useToast, type Tone } from '@onemind/ui';
import type { Action, MachineActionType, MachineParams, MachineRecord, MachineSnapshot } from '../api/types';
import { isActive } from '../data/adapters';
import { errorText, useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';
import { Load, TextField } from './parts';

const STATE: Record<string, { tone: Tone; label: string; pulse?: boolean; note?: string }> = {
  creating: { tone: 'info', label: 'Creating', pulse: true, note: 'The disk is being prepared. Nothing else can be done with it yet.' },
  needs_media: { tone: 'warn', label: 'Waiting for media', note: 'Transfer the approved files before starting this machine.' },
  stopped: { tone: 'neutral', label: 'Stopped' },
  running: { tone: 'ok', label: 'Running' },
  unknown: { tone: 'warn', label: 'Unknown', note: 'A request ended without a clear answer, so it may or may not exist in the cluster. Its name and quota stay held until an owner removes it.' },
};
const VERB: Record<MachineActionType, string> = {
  'machine.create': 'create', 'machine.start': 'start', 'machine.stop': 'stop', 'machine.delete': 'remove',
  'machine.restart': 'restart', 'machine.force_stop': 'force off', 'machine.snapshot': 'snapshot', 'machine.clone': 'clone',
  'machine.attach_device': 'attach a device', 'machine.detach_device': 'detach a device',
  'machines.enable': 'turn on', 'machines.disable': 'turn off',
};
const NAME = /^[a-z][a-z0-9-]{0,38}[a-z0-9]$/;
const RESERVED = new Set(['capabilities', 'enable', 'disable']);

export function Machines() {
  const { api } = useSignedIn();
  const hub = useHub();
  const toast = useToast();
  const caps = usePoll(async () => (api.machineCapabilities ? api.machineCapabilities() : Promise.reject(new Error('unsupported'))), 30_000);
  const list = usePoll(async () => (api.machines ? api.machines() : Promise.reject(new Error('unsupported'))), 5_000);
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState<MachineRecord>();
  const [typed, setTyped] = useState('');
  const [snapping, setSnapping] = useState<MachineRecord>();
  const [cloning, setCloning] = useState<MachineRecord>();
  const [viewing, setViewing] = useState<MachineRecord>();
  const [newName, setNewName] = useState('');
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const blocked = hub.canRequest === 'no';
  const supported = !!api.machines;

  const open = hub.actionList.filter((a) => a.type.startsWith('machine.') && isActive(a));
  const openFor = (name: string) => open.filter((a) => a.params.name === name);

  const send = async (type: MachineActionType, params: MachineParams): Promise<boolean> => {
    if (sending.current || blocked) return false;
    sending.current = true;
    setBusy(true);
    try {
      await hub.requestMachine(type, params);
      toast.show({ tone: 'info', title: 'Request sent', body: `It waits in Approvals. The machine is not touched until an owner approves it to ${VERB[type]}.` });
      void list.reload();
      return true;
    } catch (e) {
      toast.show({ tone: 'bad', title: `Could not request ${VERB[type]}`, body: errorText(e).message });
      return false;
    } finally {
      sending.current = false;
      setBusy(false);
    }
  };

  const turnOn = async () => {
    if (await send('machines.enable', {})) void caps.reload();
  };

  const submitRemove = async () => {
    const m = removing;
    if (!m || typed !== m.name) return;
    if (await send('machine.delete', { name: m.name, confirm: typed })) { setRemoving(undefined); setTyped(''); }
  };

  const nameProblem = (n: string) => {
    if (!n) return undefined;
    if (!NAME.test(n)) return 'Use 2 to 40 characters: lower-case letters, digits and dashes, starting with a letter.';
    if (RESERVED.has(n)) return `${n} is reserved: pick another name.`;
    return undefined;
  };
  const snapProblem = nameProblem(newName);
  const cloneProblem = snapProblem ?? ((list.data ?? []).some((m) => m.name === newName) ? 'A machine with this name already exists.' : undefined);
  const submitSnapshot = async () => {
    if (!snapping || !newName || snapProblem) return;
    if (await send('machine.snapshot', { name: snapping.name, snapshot: newName })) { setSnapping(undefined); setNewName(''); }
  };
  const submitClone = async () => {
    if (!cloning || !newName || cloneProblem) return;
    if (await send('machine.clone', { source: cloning.name, name: newName })) { setCloning(undefined); setNewName(''); }
  };

  const eligible = caps.data ? caps.data.eligible_node_ids.length > 0 : undefined;
  const reasons = caps.data ? [...new Set(caps.data.nodes.flatMap((n) => n.reasons.map((r) => r.message)))] : [];
  const ext = caps.data?.extension.state;
  const on = caps.data?.enabled === true;
  const turningOn = hub.actionList.some((a) => a.type === 'machines.enable' && isActive(a)) || ext === 'installing';
  const canTurnOn = !on && !turningOn && eligible === true && !blocked && !busy && ext !== 'unavailable' && ext !== 'removing';
  const waitingCreates = open.filter((a) => a.type === 'machine.create' && !(list.data ?? []).some((m) => m.name === a.params.name));

  return (
    <>
      <PageHeader
        title="Machines"
        lede="Virtual machines on this box. Every change here is a request: it waits in Approvals and nothing runs until an owner approves it."
        actions={on
          ? <Button variant="primary" disabled={!supported || blocked || eligible !== true} onClick={() => setCreating(true)}>Request a machine</Button>
          : <Button variant="primary" disabled={!supported || !canTurnOn} aria-describedby="machines-status" onClick={() => void turnOn()}>{turningOn ? 'Turning on, waiting' : 'Turn on'}</Button>}
      />
      {!supported && <p className="om-note om-tone-warn" role="status">This gateway connection has no machines route (demo data has none). Sign in to a real gateway to see machines.</p>}
      {supported && caps.data && (
        <p id="machines-status" className={`om-note ${eligible ? 'om-tone-ok' : 'om-tone-warn'}`} role="status">
          {eligible
            ? `This box can run virtual machines (${caps.data.eligible_node_ids.length} eligible node${caps.data.eligible_node_ids.length === 1 ? '' : 's'}). ${caps.data.extension.message}${on || turningOn ? '' : ' Turning them on is a request: an owner approves it in Approvals.'}`
            : `This box cannot run virtual machines yet. ${reasons.join(' ') || 'No node has reported yet.'}`}
        </p>
      )}
      {supported && (
        <Load res={list} what="Loading machines">
          {(machines) => machines.length === 0 && waitingCreates.length === 0 ? (
            <EmptyState icon="nodes" title="No machines yet">
              <p>A machine is created stopped. Starting it is a second request, so nothing uses memory before you say so.</p>
            </EmptyState>
          ) : (
            <ul className="dash-grid" aria-label="Machines">
              {waitingCreates.map((a) => (
                <li key={a.id}>
                  <Card title={String(a.params.name)}>
                    <StatusPill tone="warn" label={a.state === 'awaiting_approval' ? 'Waiting for approval' : `Request ${a.state.replace(/_/g, ' ')}`} />
                    <p className="om-hint">Requested, not created. <Link to={href.approval(a.id)}>Open in Approvals</Link></p>
                  </Card>
                </li>
              ))}
              {machines.map((m) => <MachineCard key={m.name} m={m} pending={openFor(m.name)} disabled={blocked || busy} onSend={send} onRemove={() => { setTyped(''); setRemoving(m); }}
                onSnapshot={() => { setNewName(''); setSnapping(m); }} onClone={() => { setNewName(''); setCloning(m); }} onSnapshots={() => setViewing(m)} onTransferred={() => void list.reload()} />)}
            </ul>
          )}
        </Load>
      )}
      {creating && <MachineCreateForm catalogue={caps.data?.image_catalogue ?? []} names={(list.data ?? []).map((m) => m.name)}
        busy={busy} onClose={() => setCreating(false)} onSend={(params) => send('machine.create', params)} />}
      <Dialog open={!!removing} role="alertdialog" onClose={() => setRemoving(undefined)} title={`Request removal of ${removing?.name ?? ''}`}
        description="Removing a machine erases its disk and all of its snapshots, and cannot be undone. Type its name to confirm; an owner still has to approve."
        actions={<><Button variant="ghost" onClick={() => setRemoving(undefined)}>Cancel</Button><Button variant="danger" disabled={typed !== removing?.name || busy} onClick={() => void submitRemove()}>Send removal request</Button></>}>
        <TextField id="machine-confirm" label="Machine name" value={typed} onChange={setTyped} />
      </Dialog>
      <Dialog open={!!snapping} onClose={() => setSnapping(undefined)} title={`Request a snapshot of ${snapping?.name ?? ''}`}
        description="A snapshot is a saved copy of the disk you can come back to. A running machine is paused briefly through its guest agent; if that fails the copy is best effort. An owner approves this request."
        actions={<><Button variant="ghost" onClick={() => setSnapping(undefined)}>Cancel</Button><Button variant="primary" disabled={!newName || !!snapProblem || busy} onClick={() => void submitSnapshot()}>Send request</Button></>}>
        <TextField id="snapshot-name" label="Snapshot name" value={newName} onChange={setNewName} />
        {snapProblem && <p className="om-note om-tone-bad" role="alert">{snapProblem}</p>}
      </Dialog>
      <Dialog open={!!cloning} onClose={() => setCloning(undefined)} title={`Request a copy of ${cloning?.name ?? ''}`}
        description="The copy has its own disk, counts against this box's memory and core limits like any machine, and starts stopped with no network. An owner approves this request."
        actions={<><Button variant="ghost" onClick={() => setCloning(undefined)}>Cancel</Button><Button variant="primary" disabled={!newName || !!cloneProblem || busy} onClick={() => void submitClone()}>Send request</Button></>}>
        <TextField id="clone-name" label="Name of the copy" value={newName} onChange={setNewName} />
        {cloneProblem && <p className="om-note om-tone-bad" role="alert">{cloneProblem}</p>}
      </Dialog>
      <SnapshotsDialog machine={viewing} onClose={() => setViewing(undefined)} />
    </>
  );
}

function SnapshotsDialog({ machine, onClose }: { machine?: MachineRecord; onClose: () => void }) {
  const { api } = useSignedIn();
  const [snaps, setSnaps] = useState<MachineSnapshot[]>();
  const [failed, setFailed] = useState(false);
  const name = machine?.name;
  useEffect(() => {
    setSnaps(undefined);
    setFailed(false);
    if (!name || !api.machineSnapshots) return;
    let live = true;
    api.machineSnapshots(name).then((r) => { if (live) setSnaps(r); }, () => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [name, api]);
  return (
    <Dialog open={!!machine} onClose={onClose} title={`Snapshots of ${name ?? ''}`}
      actions={<Button variant="ghost" onClick={onClose}>Close</Button>}>
      {failed && <p className="om-note om-tone-bad" role="alert">Could not load the snapshots.</p>}
      {!failed && !snaps && <p className="om-hint">Loading snapshots</p>}
      {snaps && snaps.length === 0 && <p>No snapshots yet.</p>}
      {snaps && snaps.length > 0 && (
        <ul aria-label="Snapshots">
          {snaps.map((x) => (
            <li key={x.name}>
              <strong>{x.name}</strong>{' '}
              <StatusPill tone={x.consistency === 'quiesce_failed' || x.consistency === 'best_effort' ? 'warn' : 'ok'}
                label={x.consistency === 'quiesce_failed' || x.consistency === 'best_effort' ? 'Best effort' : 'Consistent'} />
              <p className="om-hint">{x.note}</p>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

function MachineCard({ m, pending, disabled, onSend, onRemove, onSnapshot, onClone, onSnapshots, onTransferred }: { m: MachineRecord; pending: Action[]; disabled: boolean; onSend: (t: MachineActionType, p: MachineParams) => Promise<boolean>; onRemove: () => void; onSnapshot: () => void; onClone: () => void; onSnapshots: () => void; onTransferred: () => void }) {
  const s = STATE[m.state] ?? { tone: 'warn' as Tone, label: m.state };
  const waiting = pending.length > 0;
  const { role } = useShell();
  const off = disabled || waiting || m.state === 'creating';
  return (
    <li>
      <Card title={m.name}>
        <StatusPill tone={s.tone} label={s.label} pulse={s.pulse} />
        <p>{m.ram_mb} MB memory, {m.cpus} cores, {m.disk_gb} GB disk · node {m.node_id || 'not assigned'}</p>
        {s.note && <p className="om-hint">{s.note}</p>}
        {waiting && (
          <p className="om-note om-tone-warn" role="status">
            {pending.map((a) => `${VERB[a.type as MachineActionType] ?? a.type}: ${a.state.replace(/_/g, ' ')}`).join(', ')}.{' '}
            <Link to={href.approval(pending[0]!.id)}>Open in Approvals</Link>
          </p>
        )}
        <TransferMedia machine={m} disabled={off} onTransferred={onTransferred} />
        <div className="om-row">
          {m.state === 'running' && role === 'owner' && <Link to={`/machines/${encodeURIComponent(m.name)}`} aria-label={`Open console of ${m.name}`}>Open console</Link>}
          {m.state === 'stopped' && <Button size="sm" disabled={off} aria-label={`Request start of ${m.name}`} onClick={() => void onSend('machine.start', { name: m.name })}>Request start</Button>}
          {m.state === 'running' && <Button size="sm" disabled={off} aria-label={`Request stop of ${m.name}`} onClick={() => void onSend('machine.stop', { name: m.name })}>Request stop</Button>}
          {m.state === 'running' && <Button size="sm" disabled={off} aria-label={`Request restart of ${m.name}`} onClick={() => void onSend('machine.restart', { name: m.name })}>Request restart</Button>}
          {m.state === 'running' && <Button size="sm" variant="danger" disabled={off} aria-label={`Request force off of ${m.name}`} onClick={() => void onSend('machine.force_stop', { name: m.name })}>Request force off</Button>}
          {(m.state === 'running' || m.state === 'stopped') && <Button size="sm" disabled={off} aria-label={`Request snapshot of ${m.name}`} onClick={onSnapshot}>Request snapshot</Button>}
          {m.state === 'stopped' && <Button size="sm" disabled={off} aria-label={`Request copy of ${m.name}`} onClick={onClone}>Request copy</Button>}
          <Button size="sm" variant="ghost" aria-label={`Snapshots of ${m.name}`} onClick={onSnapshots}>Snapshots</Button>
          <Button size="sm" variant="danger" disabled={off} aria-label={`Request removal of ${m.name}`} onClick={onRemove}>Request removal</Button>
        </div>
      </Card>
    </li>
  );
}

function TransferMedia({ machine, disabled, onTransferred }: { machine: MachineRecord; disabled: boolean; onTransferred: () => void }) {
  const { token } = useSignedIn();
  const { role } = useShell();
  const [transferring, setTransferring] = useState(false);
  const [result, setResult] = useState('');
  const waiting = machine.state === 'needs_media';
  if ((!waiting && !result) || role !== 'owner') return null;
  const transfer = async () => {
    setTransferring(true);
    setResult('');
    try {
      const route = '/v1/machines/{name}/upload' satisfies keyof paths;
      const sdk = new OneMind({ baseUrl: window.location.origin, token, timeoutMs: 2 * 60 * 60 * 1000, retries: 1 });
      const response = await sdk.call<components['schemas']['MachineUploadResult']>({ method: 'POST', path: route.replace('{name}', encodeURIComponent(machine.name)) });
      setResult(response.media.map((m) => `${m.volume} · SHA-256 ${m.sha256}`).join(' · '));
      onTransferred();
    } catch (e) { setResult(e instanceof Error ? e.message : 'The media transfer failed.'); }
    finally { setTransferring(false); }
  };
  return <>
    {waiting && <Button size="sm" disabled={disabled || transferring} onClick={() => void transfer()}>{transferring ? 'Transferring media…' : 'Transfer media'}</Button>}
    {result && <p role="status">{result}</p>}
  </>;
}
