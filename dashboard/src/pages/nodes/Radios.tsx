// SPDX-License-Identifier: Apache-2.0
// Radios found on the machines: one card per USB radio, from GET /v1/radios. Confirming what a radio
// is ("MeshCore companion (USB)") is a person's statement, never an agent's: the gateway refuses
// anyone but an owner, and the page offers the button to owners only. Confirming opens, probes and
// sends nothing; passing the radio on to an app is a separate approval.
import { useMemo, useState } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { usePoll } from '../../lib/hooks';
import { useSignedIn } from '../../session';
import { getJson, record, records, str } from '../records';
import { Load } from '../parts';

interface Card_ { id: string; node: string; status: string; kind: string; model: string; label: string; profile: string; confirmed: boolean; at: string }

function cards(value: unknown): Card_[] {
  return records(value).map((r) => {
    const c = r.confirm && typeof r.confirm === 'object' ? record(r.confirm) : undefined;
    return { id: str(r.id, ''), node: str(r.hostname, str(r.node_id, 'a machine')), status: str(r.node_status, 'unknown'), kind: str(r.kind, 'radio'), model: str(r.model, ''),
      label: c ? str(c.label, '') : '', profile: c ? str(c.profile, '') : '', confirmed: c?.confirmed === true, at: c ? str(c.confirmed_at, '') : '' };
  }).filter((c) => c.id);
}
const KIND: Record<string, string> = { lora: 'LoRa radio', zigbee: 'Zigbee radio', 'zigbee-thread': 'Zigbee and Thread radio' };

export function Radios() {
  const { token, person, mock, principal } = useSignedIn();
  if (mock) return null;
  return <LiveRadios key={person} token={token} owner={principal?.role === 'owner'} />;
}

function LiveRadios({ token, owner }: { token: string; owner: boolean }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const list = usePoll(async () => cards(await getJson(sdk, '/v1/radios')), 30_000);
  const [asking, setAsking] = useState<Card_>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const confirm = async () => {
    if (!asking || busy) return;
    setBusy(true); setError('');
    try {
      await sdk.call<unknown>({ method: 'POST', path: `/v1/radios/${encodeURIComponent(asking.id)}/confirm`, body: { profile: asking.profile } });
      setAsking(undefined); await list.reload();
    } catch (e) {
      setError(e instanceof OneMindError && e.status === 409 ? `${e.message}. Check that the machine is online and the radio is still plugged in.` : e instanceof OneMindError && e.status === 403 ? 'Only an owner can confirm a radio.' : e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };
  return <section aria-label="Radios">
    <Load res={list} what="Looking for radios">{(items) => <Card title="Radios">
      {items.length === 0 ? <p>No radios found. Plug a LoRa, Zigbee or Thread radio into a machine and it appears here.</p> : <ul>{items.map((c) => <li key={c.id}>
        <strong>{KIND[c.kind] ?? c.kind}</strong>{c.model ? ` (${c.model})` : ''} on {c.node} <StatusPill tone={c.status === 'online' ? 'ok' : 'neutral'} label={c.status} />
        {c.profile && (c.confirmed
          ? <p>Confirmed as {c.label || c.profile}{c.at ? ` on ${c.at}` : ''}.</p>
          : <p>Not confirmed yet. {owner ? <Button size="sm" onClick={() => { setError(''); setAsking(c); }}>Confirm what this is</Button> : 'Only an owner can confirm what a radio is.'}</p>)}
      </li>)}</ul>}
      <p className="om-note">Confirming only records what the radio is. It does not open the radio or send anything, and it never gives an app access.</p>
    </Card>}</Load>
    <Dialog open={!!asking} role="alertdialog" title="Confirm this radio" onClose={() => { if (!busy) setAsking(undefined); }} actions={<Button disabled={busy} onClick={() => void confirm()}>{busy ? 'Confirming…' : 'Yes, confirm'}</Button>}>
      <p>Is the radio on <strong>{asking?.node}</strong> a <strong>{asking?.label || asking?.profile}</strong>? Only you can say, because the machine cannot tell.</p>
      <p>Plug it into the same USB port next time and it stays confirmed. A different port asks again.</p>
      {error && <p role="alert">{error}</p>}
    </Dialog>
  </section>;
}
