// SPDX-License-Identifier: Apache-2.0
// Radios found on the machines: one card per USB radio, from GET /v1/radios. Confirming what a radio
// is ("MeshCore companion (USB)") is a person's statement, never an agent's: the gateway refuses
// anyone but an owner, and the page offers the button to owners only. Confirming opens, probes and
// sends nothing; passing the radio on to an app is a separate approval.
import { useMemo, useState } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { usePoll } from '../../lib/hooks';
import { useSignedIn } from '../../session';
import { useShell } from '../../shell/Shell';
import { getJson } from '../records';
import { Load } from '../parts';

type RadioCard = components['schemas']['RadioCard'];
/** A known radio: it has an id the confirm route takes. Other USB serial lines are never named. */
type Radio = RadioCard & { id: string };

function known(value: RadioCard[]): Radio[] {
  if (!Array.isArray(value)) throw new Error('The hub returned something this page does not understand.');
  return value.filter((c): c is Radio => typeof c.id === 'string' && c.id !== '');
}
const nodeName = (c: RadioCard) => c.hostname || c.node_id || 'a machine';
const KIND: Record<string, string> = { lora: 'LoRa radio', zigbee: 'Zigbee radio', 'zigbee-thread': 'Zigbee and Thread radio' };

export function Radios() {
  const { token, person, mock } = useSignedIn();
  const { role } = useShell(); // a real hub's session has no principal; the role comes from GET /v1/me
  if (mock) return null;
  return <LiveRadios key={person} token={token} owner={role === 'owner'} />;
}

function LiveRadios({ token, owner }: { token: string; owner: boolean }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const list = usePoll(async () => known(await getJson<RadioCard[]>(sdk, '/v1/radios')), 30_000);
  const [asking, setAsking] = useState<Radio>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const confirm = async () => {
    if (!asking || busy) return;
    setBusy(true); setError('');
    try {
      await sdk.call<unknown>({ method: 'POST', path: `/v1/radios/${encodeURIComponent(asking.id)}/confirm`, // The card names the profile the gateway asks about; the request type pins today's only one.
      body: { profile: asking.confirm?.profile ?? '' } as components['schemas']['RadioConfirmRequest'] });
      setAsking(undefined); await list.reload();
    } catch (e) {
      setError(e instanceof OneMindError && e.status === 409 ? `${e.message}. Check that the machine is online and the radio is still plugged in.` : e instanceof OneMindError && e.status === 403 ? 'Only an owner can confirm a radio.' : e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };
  return <section aria-label="Radios">
    <Load res={list} what="Looking for radios">{(items) => <Card title="Radios">
      {items.length === 0 ? <p>No radios found. Plug a LoRa, Zigbee or Thread radio into a machine and it appears here.</p> : <ul>{items.map((c) => <li key={c.id}>
        <strong>{KIND[c.kind ?? ''] ?? c.kind ?? 'Radio'}</strong>{c.model ? ` (${c.model})` : ''} on {nodeName(c)} <StatusPill tone={c.node_status === 'online' ? 'ok' : 'neutral'} label={c.node_status} />
        {c.confirm && (c.confirm.confirmed
          ? <p>Confirmed as {c.confirm.label || c.confirm.profile}{c.confirm.confirmed_at ? ` on ${c.confirm.confirmed_at}` : ''}.</p>
          : <p>Not confirmed yet. {owner ? <Button size="sm" onClick={() => { setError(''); setAsking(c); }}>Confirm what this is</Button> : 'Only an owner can confirm what a radio is.'}</p>)}
      </li>)}</ul>}
      <p className="om-note">Confirming only records what the radio is. It does not open the radio or send anything, and it never gives an app access.</p>
    </Card>}</Load>
    <Dialog open={!!asking} role="alertdialog" title="Confirm this radio" onClose={() => { if (!busy) setAsking(undefined); }} actions={<Button disabled={busy} onClick={() => void confirm()}>{busy ? 'Confirming…' : 'Yes, confirm'}</Button>}>
      <p>Is the radio on <strong>{asking ? nodeName(asking) : ''}</strong> a <strong>{asking?.confirm?.label || asking?.confirm?.profile}</strong>? Only you can say, because the machine cannot tell.</p>
      <p>Plug it into the same USB port next time and it stays confirmed. A different port asks again.</p>
      {error && <p role="alert">{error}</p>}
    </Dialog>
  </section>;
}
