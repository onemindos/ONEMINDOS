// SPDX-License-Identifier: Apache-2.0
// Add a backup destination (POST /v1/backups/destinations). Credentials are write-only: they are
// sent once with the request and never shown again, and the request waits for the owner's approval.
import { useId, useState, type FormEvent } from 'react';
import { Button } from '../components/Button';
import { Dialog } from '../components/Dialog';
import { KIND_LABEL } from './logic';
import type { DestinationKind } from './types';

export interface DestinationRequest {
  kind: DestinationKind;
  label: string;
  primary: boolean;
  config: Record<string, string | boolean>;
  credentials?: Record<string, string>;
}

const KINDS: DestinationKind[] = ['usb', 'box', 's3'];

export function DestinationForm({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; onSubmit: (r: DestinationRequest) => void }) {
  const id = useId();
  const [kind, setKind] = useState<DestinationKind>('usb');
  const [f, setF] = useState<Record<string, string>>({});
  const [error, setError] = useState<string>();
  const set = (k: string) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const field = (k: string, label: string, opts: { type?: string; hint?: string; auto?: string } = {}) => (
    <label className="omb-field" htmlFor={`${id}-${k}`}>
      <span>{label}</span>
      <input id={`${id}-${k}`} type={opts.type ?? 'text'} value={f[k] ?? ''} onChange={set(k)} autoComplete={opts.auto ?? 'off'} spellCheck={false} />
      {opts.hint && <span className="om-hint">{opts.hint}</span>}
    </label>
  );

  function submit(e: FormEvent) {
    e.preventDefault();
    const label = (f.label ?? '').trim() || KIND_LABEL[kind];
    let req: DestinationRequest;
    if (kind === 'usb') {
      if (!/^[A-Za-z0-9-]{1,64}$/.test(f.usb_uuid ?? '')) return setError('Enter the disk’s filesystem UUID (shown under Storage).');
      req = { kind, label, primary: false, config: { usb_uuid: f.usb_uuid! } };
    } else if (kind === 'box') {
      if (!(f.url ?? '').startsWith('https://') || !f.user || !f.password) return setError('The other box’s address (https://…), user and password are all needed.');
      req = { kind, label, primary: false, config: { url: f.url!, user: f.user, append_only: true }, credentials: { password: f.password } };
    } else {
      if (!(f.endpoint ?? '').startsWith('https://') || !f.bucket || !f.access_key || !f.secret_key) return setError('Endpoint (https://…), bucket and both keys are needed.');
      req = { kind, label, primary: false, config: { endpoint: f.endpoint!, bucket: f.bucket, ...(f.prefix ? { prefix: f.prefix } : {}) },
        credentials: { access_key: f.access_key, secret_key: f.secret_key } };
    }
    setError(undefined);
    setF({});
    onSubmit(req);
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a backup destination"
      description="It is added after you approve the request. Passwords and keys are sent once and never shown again."
      actions={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" type="submit" form={`${id}-form`}>Request</Button></>}
    >
      <form id={`${id}-form`} className="omb-form" onSubmit={submit} noValidate>
        <fieldset className="omb-kinds">
          <legend className="om-subhead">Kind</legend>
          {KINDS.map((k) => (
            <label key={k} className="omb-kind">
              <input type="radio" name={`${id}-kind`} value={k} checked={kind === k} onChange={() => { setKind(k); setError(undefined); }} />
              {KIND_LABEL[k]}
            </label>
          ))}
        </fieldset>
        {field('label', 'Name', { hint: 'For you, e.g. “Blue USB disk” or “Garage box”.' })}
        {kind === 'usb' && field('usb_uuid', 'Disk UUID', { hint: 'Unplug it and store it away sometimes: an unplugged disk is the safest copy.' })}
        {kind === 'box' && (
          <>
            {field('url', 'Address', { hint: 'The other box keeps your backups append-only: this box can add but never delete them.' })}
            {field('user', 'User')}
            {field('password', 'Password', { type: 'password', auto: 'new-password' })}
          </>
        )}
        {kind === 's3' && (
          <>
            {field('endpoint', 'Endpoint')}
            {field('bucket', 'Bucket')}
            {field('prefix', 'Folder in the bucket (optional)')}
            {field('access_key', 'Access key', { auto: 'off' })}
            {field('secret_key', 'Secret key', { type: 'password', auto: 'new-password' })}
          </>
        )}
        {error && <p className="omb-error" role="alert">{error}</p>}
      </form>
    </Dialog>
  );
}
