// SPDX-License-Identifier: Apache-2.0
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { Button, Card, EmptyState, PageHeader } from '@onemind/ui';
import type { OneMindApi } from '../api/client';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { Load, TextField, useRun } from './parts';

type KeysApi = Required<Pick<OneMindApi, 'pluginSigningKeys' | 'requestPluginSigningKey' | 'revokePluginSigningKey'>>;

export function PluginKeys() {
  const { api } = useSignedIn();
  if (!api.pluginSigningKeys || !api.requestPluginSigningKey || !api.revokePluginSigningKey) {
    return <EmptyState icon="settings" title="Connect to a gateway to manage plugin signing trust" />;
  }
  return <ConnectedPluginKeys api={api as OneMindApi & KeysApi} />;
}

function ConnectedPluginKeys({ api }: { api: KeysApi }) {
  const hub = useHub();
  const run = useRun();
  const keys = usePoll(() => api.pluginSigningKeys(), 5000);
  const [name, setName] = useState('');
  const [publicKey, setPublicKey] = useState('');
  const [pending, setPending] = useState('');
  const [busy, setBusy] = useState(false);
  const privateInput = publicKey.includes('PRIVATE KEY');
  const requestFields = () => ({ idempotency_key: crypto.randomUUID(), expires_at: new Date(hub.now + 600000).toISOString() });
  const enroll = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || keys.error || privateInput || !name.trim() || !publicKey.trim()) return;
    setBusy(true);
    try {
      await run(async () => {
        const action = await api.requestPluginSigningKey({ name: name.trim(), public_key: publicKey.trim(), ...requestFields() });
        setPending(action.id);
        setPublicKey('');
        await keys.reload();
      }, 'Request signing-key enrollment');
    } finally { setBusy(false); }
  };
  const revoke = async (id: string) => {
    if (busy || keys.error) return;
    setBusy(true);
    try {
      await run(async () => {
        const action = await api.revokePluginSigningKey(id, requestFields());
        setPending(action.id);
      }, 'Request signing-trust revocation');
    } finally { setBusy(false); }
  };
  return <div className="dash-stack">
    <PageHeader title="Plugin signing keys" lede="Owner-enrolled keys for private plugins. Enrollment and revocation both wait for approval." />
    <Link to="/settings/about">Back to settings</Link>
    {pending && <p role="status">Request {pending} was filed. <Link to="/approvals">Review the fingerprint in Approvals</Link>.</p>}
    {keys.error && keys.data && <p role="status">Could not refresh signing trust; showing the last response. <Button variant="ghost" onClick={() => void keys.reload()}>Retry</Button></p>}
    <Load res={keys} what="Loading plugin signing trust">{data => <>
      <Card title="Enroll a public signing key">
        <form className="dash-form" onSubmit={event => void enroll(event)}>
          <TextField id="plugin-key-name" label="Key label" value={name} onChange={setName} />
          <label htmlFor="plugin-key-public">Public key PEM</label>
          <textarea id="plugin-key-public" value={publicKey} onChange={event => setPublicKey(event.target.value)} rows={6} maxLength={16384} aria-describedby="plugin-key-hint" />
          <p id="plugin-key-hint">Paste a PUBLIC KEY block. Keep the private key on your signing machine.</p>
          {privateInput && <p role="alert">Private keys are not accepted. Export the public key instead.</p>}
          <Button type="submit" disabled={busy || !!keys.error || privateInput || !name.trim() || !publicKey.trim()}>Request enrollment</Button>
        </form>
      </Card>
      <Card title="Signing trust on this box">
        {data.keys.length === 0 ? <p>No signing keys have been enrolled.</p> : <ul>{data.keys.map(key => <li key={key.id}>
          <strong>{key.name}</strong> — {key.active ? 'Active' : 'Revoked'}<br /><code style={{ overflowWrap: 'anywhere' }}>{key.id}</code>
          {key.active && <Button disabled={busy || !!keys.error} variant="ghost" onClick={() => void revoke(key.id)}>Request revocation</Button>}
        </li>)}</ul>}
      </Card>
    </>}</Load>
  </div>;
}
