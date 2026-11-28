// SPDX-License-Identifier: Apache-2.0
// Network, change a cable connection (P-08): a fixed address and DNS, or back to DHCP, with an automatic way back.
// The form only ASKS (PUT /v1/network/{iface} files an action); an owner approves it with a passkey in Approvals.
// After approval the box applies it, and this card asks the owner to check the new address before confirming:
// no confirmation, and the box puts its old settings back by itself, so a wrong address never strands anyone.
import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { OneMindError, type Action, type NetworkView, type OneMind } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { uuidv4 } from '../lib/uuid';
import { href } from '../shell/routes';

type Changes = NonNullable<NetworkView['changes']>;
type Pending = NonNullable<Changes['pending']>;

const WINDOWS = [60, 120, 300];

function words(e: unknown): string {
  return e instanceof OneMindError || e instanceof Error ? e.message : 'The request failed.';
}

function describe(c: { mode: string; address?: string | null }): string {
  return c.mode === 'dhcp' ? 'an automatic (DHCP) address' : `the fixed address ${c.address ?? ''}`;
}

export function secondsLeft(deadline: string, now: number): number {
  return Math.max(0, Math.ceil((Date.parse(deadline) - now) / 1000));
}

function Confirm({ client, pending, onDone, onExpired }: { client: OneMind; pending: Pending; onDone: () => void; onExpired: () => void }) {
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [verified, setVerified] = useState(false);
  const actionId = pending.action_id;
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const left = secondsLeft(pending.deadline, now);
  useEffect(() => {
    if (left > 0) return;
    const t = window.setTimeout(onExpired, 4000); // the box rolled back by itself: read the network again (this is NOT a confirmation)
    return () => window.clearTimeout(t);
  }, [left, onExpired]);
  const confirm = async () => {
    if (!verified || !actionId || left <= 0) return;
    setBusy(true);
    setErr(null);
    try {
      await client.network.confirm(pending.interface, { action_id: actionId, verified_reachable: true });
      onDone();
    } catch (e) {
      setErr(words(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card as="article" title="Confirm the new address">
      <p role="status">
        {pending.interface} now has {describe(pending)}.
        {left > 0 ? <> Without confirmation the box goes back to its old settings in <strong>{left} s</strong>.</> : <> The time is up: the box is going back to its old settings.</>}
      </p>
      {actionId ? (
        <>
          <p className="om-hint">
            {pending.mode === 'dhcp' && 'Find the IPv4 address your router assigned to this interface. '}
            Open the box at {pending.address?.split('/')[0] ?? 'that IPv4 address'} from another device on the wired network. Sign in and verify that this box&apos;s Network page loads.
          </p>
          <p><label><input type="checkbox" checked={verified} onChange={(event) => setVerified(event.target.checked)} /> I verified the Network page at the new IPv4 address.</label></p>
          <Button variant="primary" disabled={busy || !verified || left <= 0} onClick={() => void confirm()}>
            Confirm {pending.interface}
          </Button>
        </>
      ) : <p className="om-hint">Wait for this change to roll back before requesting it again. Its approval ID is missing.</p>}
      {err && <p className="om-note om-tone-warn" role="alert">{err}</p>}
    </Card>
  );
}

export function NetworkChange({ client, view, onChanged }: { client: OneMind; view: NetworkView; onChanged: () => void }) {
  const ethernet = view.interfaces.filter((i) => i.kind === 'ethernet');
  const changes = view.changes ?? null;
  const [iface, setIface] = useState('');
  const [mode, setMode] = useState<'dhcp' | 'static'>('static');
  const [address, setAddress] = useState('');
  const [gateway, setGateway] = useState('');
  const [dns, setDns] = useState('');
  const [seconds, setSeconds] = useState(120);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [filed, setFiled] = useState<{ action: Action; where: string; seconds: number } | null>(null);
  const [kept, setKept] = useState(false);
  const chosen = iface || ethernet[0]?.name || '';

  if (!changes) return null; // an older gateway: this page cannot change anything
  if (changes.pending) {
    return <Confirm key={changes.pending.action_id} client={client} pending={changes.pending} onDone={() => { setKept(true); onChanged(); }} onExpired={onChanged} />;
  }
  const rolledBack = changes.last?.result === 'rolled_back' ? changes.last : null;
  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    setBusy(true);
    setErr(null);
    setFiled(null);
    try {
      const servers = dns.split(/[\s,]+/).filter(Boolean);
      const body = mode === 'dhcp'
        ? { mode, rollback_seconds: seconds, idempotency_key: uuidv4() }
        : { mode, address: address.trim(), gateway: gateway.trim(), dns: servers, rollback_seconds: seconds, idempotency_key: uuidv4() };
      const action = await client.network.configure(chosen, body);
      setFiled({ action, where: mode === 'dhcp' ? 'the address your router gives it' : address.trim().split('/')[0] ?? '', seconds });
    } catch (e) {
      setErr(words(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card as="article" title="Change a cable connection">
      {kept && <p role="status">Confirmed. The change stays, also after a restart.</p>}
      {rolledBack && !kept && (
        <p className="om-note om-tone-warn" role="status">
          The last change to {rolledBack.interface} was not confirmed in time, so the box went back to its old settings.
        </p>
      )}
      {!changes.can_change ? (
        <p className="om-note om-tone-warn" role="status">{changes.reason ?? 'This box cannot change its network from here.'}</p>
      ) : ethernet.length === 0 ? (
        <p>No cable connection was found on this box.</p>
      ) : (
        <form onSubmit={(e) => void submit(e)} aria-label="Change a cable connection">
          <p>
            Give a cable connection a fixed address, or hand it back to your router (DHCP). An owner approves the request with a passkey, then you have {seconds} seconds to open the box at its new address and confirm; if you cannot, it goes back by itself.
          </p>
          <p>
            <label>
              Connection
              <select value={chosen} onChange={(e) => setIface(e.target.value)}>
                {ethernet.map((i) => <option key={i.name} value={i.name}>{i.name}{i.addresses.length > 0 ? ` (${i.addresses[0]})` : ''}</option>)}
              </select>
            </label>
          </p>
          <fieldset>
            <legend>Address</legend>
            <label><input type="radio" name="net-mode" checked={mode === 'dhcp'} onChange={() => setMode('dhcp')} /> Automatic (DHCP): the router decides</label>{' '}
            <label><input type="radio" name="net-mode" checked={mode === 'static'} onChange={() => setMode('static')} /> Fixed address</label>
          </fieldset>
          {mode === 'static' && (
            <>
              <p><label>IP address with prefix<input required inputMode="decimal" placeholder="192.0.2.20/24" maxLength={18} value={address} onChange={(e) => setAddress(e.target.value)} /></label></p>
              <p><label>Router (gateway)<input required inputMode="decimal" placeholder="192.0.2.1" maxLength={15} value={gateway} onChange={(e) => setGateway(e.target.value)} /></label></p>
              <p><label>DNS servers (optional, up to three)<input placeholder="192.0.2.1, 1.1.1.1" maxLength={60} value={dns} onChange={(e) => setDns(e.target.value)} /></label></p>
            </>
          )}
          <p>
            <label>
              Time to confirm
              <select value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}>
                {WINDOWS.map((s) => <option key={s} value={s}>{s} seconds</option>)}
              </select>
            </label>
          </p>
          <Button type="submit" variant="primary" disabled={busy}>Ask to change</Button>
        </form>
      )}
      {err && <p className="om-note om-tone-warn" role="alert">{err}</p>}
      {filed && (
        <p role="status">
          Request {filed.action.id} waits for an owner&apos;s passkey. <Link to={href.approval(filed.action.id)}>Open request in Approvals</Link>.
          After approving, open the box at {filed.where} and press Confirm on this page within {filed.seconds} seconds.
        </p>
      )}
    </Card>
  );
}
