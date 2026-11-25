// SPDX-License-Identifier: Apache-2.0
// Add a backup destination (usb, box, rest, s3) as an approval request: POST /v1/backups/destinations.
// Credentials are write-only: held in memory, sent once, cleared on success, never stored or shown again.
import { useState } from 'react';
import { Link } from 'react-router';
import type { OneMind } from '@onemind/sdk';
import { Button, Dialog } from '@onemind/ui';
import { href } from '../../shell/routes';
import { TextField } from '../parts';
import { useFiling } from './shared';

const KINDS = [
  { id: 'usb', label: 'USB disk', hint: 'A disk plugged into this box, found by its filesystem UUID.' },
  { id: 'box', label: 'Another OneMind box', hint: 'Append-only: this box can add backups but not erase them.' },
  { id: 'rest', label: 'Restic REST server', hint: 'Your own server speaking the restic REST protocol, over https.' },
  { id: 's3', label: 'S3 off-site bucket', hint: 'Off-site copy in an S3-compatible bucket, over https.' },
] as const;
type Kind = (typeof KINDS)[number]['id'];
const FIELDS: Record<Kind, { cfg: [string, string][]; cred: [string, string][] }> = {
  usb: { cfg: [['usb_uuid', 'Disk filesystem UUID']], cred: [] },
  box: { cfg: [['url', 'Address (https://…)'], ['user', 'User name']], cred: [['password', 'Repository password']] },
  rest: { cfg: [['url', 'Address (https://…)'], ['user', 'User name']], cred: [['password', 'Repository password']] },
  s3: { cfg: [['endpoint', 'Endpoint (https://…)'], ['bucket', 'Bucket'], ['prefix', 'Folder in the bucket (optional)'], ['region', 'Region (optional)']],
    cred: [['access_key', 'Access key'], ['secret_key', 'Secret key']] },
};
const OPTIONAL = new Set(['prefix', 'region']);

export function DestinationForm({ sdk, token }: { sdk: OneMind; token: string }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind>('s3');
  const [label, setLabel] = useState('');
  const [primary, setPrimary] = useState(false);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [receipt, setReceipt] = useState<{ id: string; state: string }>();
  const { file, busy, error } = useFiling(sdk, token);
  const f = FIELDS[kind];
  const all = [...f.cfg, ...f.cred];
  const missing = !label.trim() || all.some(([k]) => !OPTIONAL.has(k) && !(vals[k] ?? '').trim());
  const insecure = f.cfg.some(([k]) => ['url', 'endpoint'].includes(k) && !!vals[k] && !vals[k].startsWith('https://'));
  const close = () => { if (!busy) { setOpen(false); setVals({}); setLabel(''); setPrimary(false); } };
  const send = async () => {
    const config: Record<string, string> = {};
    for (const [k] of f.cfg) { const v = (vals[k] ?? '').trim(); if (v) config[k] = v; }
    const credentials: Record<string, string> = {};
    for (const [k] of f.cred) credentials[k] = vals[k] ?? '';
    const r = await file('/v1/backups/destinations', 'backup.destination.add', { kind, label: label.trim(), primary, config, ...(f.cred.length ? { credentials } : {}) });
    if (r) { setReceipt({ id: r.id, state: r.state }); setVals({}); setLabel(''); setPrimary(false); setOpen(false); }
  };
  return <>
    <Button variant="secondary" onClick={() => { setReceipt(undefined); setOpen(true); }}>Add destination</Button>
    {receipt && <p role="status">Request {receipt.id}: {receipt.state}. Nothing was added yet. <Link to={href.approval(receipt.id)}>Open request in Approvals</Link></p>}
    <Dialog role="alertdialog" open={open} onClose={close} title="Add a backup destination"
      description="This files a request. The destination is added only when the owner approves it."
      actions={<><Button variant="secondary" disabled={busy} onClick={close}>Cancel</Button><Button disabled={busy || missing || insecure} onClick={() => void send()}>{busy ? 'Sending request…' : error ? 'Retry same request' : 'File request'}</Button></>}>
      <label htmlFor="dest-kind">Where backups go</label>
      <select id="dest-kind" value={kind} onChange={(e) => { setKind(e.target.value as Kind); setVals({}); }}>
        {KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
      </select>
      <p className="om-hint">{KINDS.find((k) => k.id === kind)?.hint}</p>
      <TextField id="dest-label" label="Name" value={label} onChange={setLabel} />
      {all.map(([k, name]) => <TextField key={`${kind}-${k}`} id={`dest-${k}`} label={name} value={vals[k] ?? ''} onChange={(v) => setVals({ ...vals, [k]: v })}
        type={f.cred.some(([c]) => c === k) ? 'password' : 'text'} autoComplete="off" />)}
      <label><input type="checkbox" checked={primary} onChange={(e) => setPrimary(e.target.checked)} /> Make this the primary destination</label>
      {insecure && <p role="alert">The address must start with https://.</p>}
      <p className="om-hint">Keys and passwords are sent once, held by the box only after approval, and never shown again.</p>
      {error && <p role="alert">{error}</p>}
    </Dialog>
  </>;
}
