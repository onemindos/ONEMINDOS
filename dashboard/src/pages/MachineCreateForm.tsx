/* SPDX-License-Identifier: Apache-2.0 */
import { useState } from 'react';
import { Button, Dialog } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import type { MachineMedia, MachineParams, MachineSource } from '../api/types';
import { FilesApi } from '../files/api';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { TextField } from './parts';

type Image = components['schemas']['CatalogueImage'];
type FileChoice = { name: string; media: MachineMedia };
const STEPS = ['Operating system', 'Resources', 'Network', 'Review'] as const;
const GiB = 1024 ** 3;
const inRange = (value: string, min: number, max: number) => /^\d+$/.test(value) && Number(value) >= min && Number(value) <= max;

export function MachineCreateForm({ catalogue, names, busy, onClose, onSend }: {
  catalogue: Image[]; names: string[]; busy: boolean; onClose: () => void; onSend: (p: MachineParams) => Promise<boolean>;
}) {
  const { token, principal, account } = useSignedIn();
  const { role } = useShell();
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [kind, setKind] = useState<'catalogue' | 'iso' | 'disk'>(catalogue.length ? 'catalogue' : 'iso');
  const [imageUrl, setImageUrl] = useState(catalogue[0]?.url ?? '');
  const [file, setFile] = useState<FileChoice>();
  const [drivers, setDrivers] = useState<FileChoice>();
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [ram, setRam] = useState('2048');
  const [cpus, setCpus] = useState('2');
  const [disk, setDisk] = useState('20');
  const [uefi, setUefi] = useState(false);
  const [tpm, setTpm] = useState(false);
  const [peers, setPeers] = useState(false);
  const loading = !!progress || busy;
  const image = catalogue.find((entry) => entry.url === imageUrl);
  const canUpload = role === 'owner' && !!(account ?? principal)?.id; // the upload target is the person's home
  const nameProblem = !/^[a-z][a-z0-9-]{0,38}[a-z0-9]$/.test(name) ? 'Use 2 to 40 lowercase letters, digits or dashes, starting with a letter.'
    : ['capabilities', 'enable', 'disable', ...names].includes(name) ? 'Choose another machine name. This one is reserved or already in use.' : '';
  const source: MachineSource | undefined = kind === 'catalogue' ? image && { kind, url: image.url, sha256: image.sha256 }
    : file && { kind, ...file.media };
  const fitsDisk = kind !== 'disk' || !file || file.media.size_bytes <= Number(disk) * GiB;
  const validResources = inRange(ram, 512, 262144) && inRange(cpus, 1, 64) && inRange(disk, 1, 2048) && fitsDisk;
  const next = step === 0 ? !!source && !nameProblem && !error : step === 1 ? validResources : true;

  async function stage(chosen: File | undefined, driver: boolean) {
    if (!chosen || !canUpload || loading) return;
    const set = driver ? setDrivers : setFile;
    set(undefined);
    setError('');
    const limit = driver || kind === 'iso' ? 16 : 2048;
    if (chosen.size === 0 || chosen.size > limit * GiB) { setError(`Choose a nonempty file no larger than ${limit} GiB.`); return; }
    const files = new FilesApi(token);
    // Each staging copy gets a distinct Home filename, even for two different installation.iso files.
    const stored = new File([chosen], `${crypto.randomUUID()}-${chosen.name}`);
    setProgress(`Uploading ${chosen.name}…`);
    try {
      const location = await files.upload(stored, `home:${(account ?? principal)?.id}`, '/', (done) => setProgress(`Uploading ${chosen.name}: ${Math.round(100 * done / chosen.size)}%`));
      const media = await files.completedUpload(location);
      if (media.size_bytes !== chosen.size) throw new Error('The stored upload size differs from the file you selected.');
      set({ name: chosen.name, media });
    } catch (e) { setError(e instanceof Error ? e.message : 'The media upload failed. Choose the file again.'); }
    finally { setProgress(''); }
  }

  const params: MachineParams = {
    name, source, ram_mb: Number(ram), cpus: Number(cpus), disk_gb: Number(disk),
    firmware: uefi ? 'uefi' : 'bios', tpm, network: peers ? 'machine_peers' : 'isolated',
    ...(kind === 'iso' && drivers ? { virtio_drivers: drivers.media } : {}),
  };
  async function advance() {
    if (!next || loading) return;
    if (step < 3) { setStep(step + 1); return; }
    if (source && !nameProblem && validResources && await onSend(params)) onClose();
  }
  const network = peers ? 'Other participating machines on this hub' : 'Isolated (all traffic denied)';
  return <Dialog open title="Request a machine" onClose={() => { if (!loading) onClose(); }}
    actions={<>
      <Button variant="ghost" disabled={loading} onClick={onClose}>Cancel</Button>
      {step > 0 && <Button disabled={loading} onClick={() => setStep(step - 1)}>Back</Button>}
      <Button variant="primary" disabled={!next || loading} onClick={() => void advance()}>{step === 3 ? 'Send request' : 'Continue'}</Button>
    </>}>
    <form className="dash-form" onSubmit={(e) => { e.preventDefault(); void advance(); }}>
      <h3>{STEPS[step]} <small>({step + 1} of 4)</small></h3>
      {step === 0 && <>
        <TextField id="machine-name" label="Name" value={name} onChange={setName} />
        {name && nameProblem && <p role="alert">{nameProblem}</p>}
        <label htmlFor="machine-source">Image source</label>
        <select id="machine-source" disabled={loading} value={kind} onChange={(e) => { setKind(e.target.value as typeof kind); setFile(undefined); setDrivers(undefined); setError(''); }}>
          <option value="catalogue" disabled={!catalogue.length}>Cloud image catalogue</option>
          <option value="iso" disabled={!canUpload}>My installer ISO</option>
          <option value="disk" disabled={!canUpload}>My disk image</option>
        </select>
        {kind === 'catalogue' ? <>
          <label htmlFor="machine-image">Cloud image</label>
          <select id="machine-image" value={imageUrl} onChange={(e) => setImageUrl(e.target.value)}>
            {catalogue.map((entry) => <option key={entry.url} value={entry.url}>{entry.name}</option>)}
          </select>
        </> : <>
          <p>Choosing a file saves a copy in your Home and computes its SHA-256 for approval.</p>
          <label htmlFor="machine-file">{kind === 'iso' ? 'Installer ISO' : 'Disk image'}</label>
          <input id="machine-file" type="file" accept={kind === 'iso' ? '.iso' : undefined} disabled={loading || !canUpload}
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; void stage(f, false); }} />
          {file && <p>{file.name} · SHA-256 <code>{file.media.sha256}</code></p>}
          {kind === 'iso' && <>
            <label htmlFor="machine-drivers">VirtIO drivers ISO (optional)</label>
            <input id="machine-drivers" type="file" accept=".iso" disabled={loading || !canUpload}
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; void stage(f, true); }} />
            {drivers && <p>{drivers.name} · SHA-256 <code>{drivers.media.sha256}</code></p>}
            {(drivers || error) && <Button type="button" disabled={loading} onClick={() => { setDrivers(undefined); setError(''); }}>Clear optional drivers</Button>}
          </>}
        </>}
        {progress && <p role="status">{progress}</p>}{error && <p role="alert">{error}</p>}
      </>}
      {step === 1 && <>
        <TextField id="machine-cpus" type="number" label="Processor cores (1–64)" value={cpus} onChange={setCpus} />
        <TextField id="machine-ram" type="number" label="Memory (MiB, 512–262144)" value={ram} onChange={setRam} />
        <TextField id="machine-disk" type="number" label="Disk (GiB, 1–2048)" value={disk} onChange={setDisk} />
        {!fitsDisk && <p role="alert">The selected disk image exceeds this disk capacity.</p>}
        <label><input type="checkbox" checked={uefi} onChange={(e) => { setUefi(e.target.checked); if (!e.target.checked) setTpm(false); }} /> UEFI firmware with Secure Boot</label>
        <label><input type="checkbox" disabled={!uefi} checked={tpm} onChange={(e) => setTpm(e.target.checked)} /> Persistent TPM 2.0 (requires UEFI)</label>
      </>}
      {step === 2 && <fieldset><legend>Network access</legend>
        <label><input type="radio" name="machine-net" checked={!peers} onChange={() => setPeers(false)} /> Isolated</label>
        <label><input type="radio" name="machine-net" checked={peers} onChange={() => setPeers(true)} /> Connect to other participating machines on this hub</label>
      </fieldset>}
      {step === 3 && source && <>
        <dl>
          <dt>Machine</dt><dd>{name} · created stopped</dd>
          <dt>Image</dt><dd>{source.kind === 'catalogue' ? <>{image?.name}<br />{source.url}</> : <>{file?.name} ({source.size_bytes} bytes)</>}<br />SHA-256 <code>{source.sha256}</code></dd>
          {kind === 'iso' && drivers && <><dt>VirtIO drivers</dt><dd>{drivers.name} ({drivers.media.size_bytes} bytes)<br />SHA-256 <code>{drivers.media.sha256}</code></dd></>}
          <dt>Resources</dt><dd>{cpus} cores · {ram} MiB memory · {disk} GiB disk</dd>
          <dt>Firmware</dt><dd>{uefi ? 'UEFI with Secure Boot' : 'BIOS'} · TPM {tpm ? 'on' : 'off'}</dd>
          <dt>Network</dt><dd>{network}</dd>
        </dl>
        <p>An owner approves these choices in Approvals. {kind !== 'catalogue' && 'After approval, use Transfer media on the machine to finish importing.'}</p>
      </>}
    </form>
  </Dialog>;
}
