// SPDX-License-Identifier: Apache-2.0
// Nodes: one card per machine from GET /v1/nodes. Status is the gateway's verdict aged on the
// hub clock, so a stale or offline machine keeps its last values but never looks live.
import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, uuid4, type components } from '@onemind/sdk';
import { Button, Dialog, EmptyState, NodeCard, PageHeader, StateView } from '@onemind/ui';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';

type WakeRequest = components['schemas']['FeatureActionRequest'];
const pending = new Map<string, WakeRequest>();

function WakeControls({ nodeId, disabled }: { nodeId: string; disabled: boolean }) {
  const { token, person, mock } = useSignedIn();
  if (mock) return <p className="om-note">Wake unavailable in demo mode. Connect to a real hub.</p>;
  return <LiveWake key={`${person}:${nodeId}`} nodeId={nodeId} token={token} person={person} disabled={disabled} />;
}

function LiveWake({ nodeId, token, person, disabled }: { nodeId: string; token: string; person: string; disabled: boolean }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const capability = usePoll(() => sdk.call<components['schemas']['WakeCapability']>({ method: 'GET', path: `/v1/nodes/${encodeURIComponent(nodeId)}/wake` }));
  const slot = `${person}:${nodeId}`;
  const { reloadAll } = useHub();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState<string>();
  const available = !disabled && !capability.error && capability.data?.available === true
    && capability.data.params?.node_id === nodeId && /^[a-f0-9]{64}$/.test(capability.data.params.target_sha256);
  const send = async () => {
    if (!available || sending.current) return;
    sending.current = true; setBusy(true); setError('');
    const body = pending.get(slot) ?? { type: 'node.wake', params: { ...capability.data!.params! }, idempotency_key: uuid4(), expires_at: new Date(sdk.hubNow() + 600_000).toISOString() };
    pending.set(slot, body);
    try {
      const a = await sdk.call<components['schemas']['Action']>({ method: 'POST', path: '/v1/actions', body });
      if (!a || typeof a.id !== 'string' || !a.id || a.type !== 'node.wake' || a.idempotency_key !== body.idempotency_key
        || a.params?.node_id !== nodeId || a.params?.target_sha256 !== body.params.target_sha256
        || !['requested', 'awaiting_approval', 'accepted', 'dispatched', 'succeeded', 'failed', 'expired', 'cancelled', 'outcome_unknown'].includes(a.state)) {
        throw new Error('Incomplete or mismatched wake request reply');
      }
      pending.delete(slot); setReceipt(a.id); setOpen(false); reloadAll();
    } catch (e) {
      if (e instanceof OneMindError && (e.code === 'expired' || e.code === 'stale_precondition')) {
        pending.delete(slot);
        setError('The gateway refused the outdated request. Refresh availability, then send a new request.');
        void capability.reload();
      } else setError(`${e instanceof Error ? e.message : String(e)}. Retry the same request; it may already have been filed.`);
    } finally { sending.current = false; setBusy(false); }
  };
  return <div className="dash-stack">
    <Button size="sm" variant="secondary" disabled={!available || busy} onClick={() => setOpen(true)}>Request wake</Button>
    <p className="om-note">{capability.error ? 'Wake availability could not be refreshed. Controls disabled.' : capability.data?.reason ?? 'Checking wake availability…'}</p>
    {receipt && <p role="status">Wake requested. Nothing runs until owner approval; a packet does not prove the node is awake. <Link to={href.approval(receipt)}>Review wake request</Link></p>}
    <Dialog open={open} role="alertdialog" title={`Request wake: ${nodeId}`} onClose={() => { if (!busy) setOpen(false); }} actions={<Button disabled={!available || busy} onClick={() => void send()}>{busy ? 'Sending request…' : pending.has(slot) ? 'Retry same request' : 'Send request'}</Button>}>
      <p>Nothing runs until the owner approves in Approvals. The hub sends one Wake-on-LAN packet to this node’s administrator-configured target. Only a fresh heartbeat confirms it is awake.</p>
      {(!available || disabled) && <p role="status">Wake availability is stale or unavailable. Refresh before requesting.</p>}
      {error && <p role="alert">{error}</p>}
    </Dialog>
  </div>;
}


export function Nodes() {
  const hub = useHub();
  const nodes = hub.nodes.data;
  const stale = hub.freshness === 'stale' || hub.freshness === 'offline';
  return (
    <>
      <PageHeader title="Nodes" lede="The machines in this OneMind. Each sends a heartbeat every 10 s; after 30 s without one it is stale, after 2 minutes offline." />
      <p><Link to="/add-machine">Add a machine</Link></p>
      {nodes === undefined ? (
        hub.nodes.error ? (
          <StateView state="error" error={{ error: hub.nodes.error.code === 'network' ? 'unreachable' : hub.nodes.error.code === 'unauthenticated' ? 'unauthenticated' : 'not_found', message: hub.nodes.error.message }} onRetry={hub.reloadAll} />
        ) : (
          <StateView state="loading" what="Loading nodes" skeleton="list" />
        )
      ) : nodes.length === 0 ? (
        <EmptyState icon="nodes" title="No machines have reported yet" command="onemind node join">
          <p>The hub lists a machine after its first heartbeat. <Link to="/add-machine">Add a machine</Link> to join one.</p>
        </EmptyState>
      ) : (
        <>
          {stale && (
            <p className="om-note om-tone-warn" role="status">
              The hub has not answered for a while. These are the last values it sent, not live.
            </p>
          )}
          <ul className="dash-grid" aria-label="Nodes">
            {nodes.map((n) => (
              <li key={n.node_id}>
                <NodeCard node={{ ...n, status: hub.nodeStatus(n) }} now={hub.now}
                  actions={<WakeControls nodeId={n.node_id} disabled={hub.freshness !== 'live' || !!hub.nodes.error || hub.canRequest === 'no'} />} />
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
