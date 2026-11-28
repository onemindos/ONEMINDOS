// SPDX-License-Identifier: Apache-2.0
// Add a machine (UI sprint P0, #239/#251; CORE-FABRIC join flow). The owner makes a one-time join
// ticket (QR plus the install command), the new machine asks to join with that code, and the
// request lands in Approvals as a sensitive node.join action: nothing joins without an owner's
// approval (and a passkey where the gateway asks). Also shows the mesh and the box CA with its
// download. The join code is shown once, kept only in this window's state, and forgotten on close.
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { AddDevice, Card, NetworkPage, PageHeader, type FabricSummary, type Loadable, type MeshView } from '@onemind/ui';
import { usePoll, type Polled } from '../lib/hooks';
import { useHub } from '../data/hub';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { href } from '../shell/routes';

function loadable<T>(p: Polled<T>): Loadable<T> {
  if (p.data !== undefined) return { state: 'ok', data: p.data };
  if (p.error) return { state: 'error', message: p.error.code === 'network' ? 'the hub did not answer' : p.error.message };
  return { state: 'loading' };
}

export function AddMachine() {
  const { api } = useSignedIn();
  const { role } = useShell();
  const hub = useHub();
  const navigate = useNavigate();
  const [adding, setAdding] = useState(false);
  const supported = !!(api.meshView && api.fabricSummary && api.createJoinTicket);
  const mesh = usePoll<MeshView>(() => (api.meshView ? api.meshView() : Promise.reject(new Error('unsupported'))), 15_000);
  const fabric = usePoll<FabricSummary>(() => (api.fabricSummary ? api.fabricSummary() : Promise.reject(new Error('unsupported'))), adding ? 3_000 : 15_000);
  const tls = usePoll(() => (api.tlsInfo ? api.tlsInfo() : Promise.reject(new Error('unsupported'))), 60_000);
  const isOwner = role === 'owner';

  if (!supported) {
    return (
      <>
        <PageHeader title="Add a machine" lede="Join another computer to this OneMind." />
        <p className="om-note om-tone-warn" role="status">This hub does not offer join tickets. On the new machine, run <code>onemind fabric join</code> with a code from a hub that does.</p>
      </>
    );
  }
  const reload = () => { void mesh.reload(); void fabric.reload(); void tls.reload(); };
  const m = loadable(mesh);
  const f = loadable(fabric);
  return (
    <>
      <PageHeader title="Add a machine" lede="Make a one-time code, enter it on the new machine, then approve the request it files. Nothing joins until you approve." />
      {!isOwner && role !== undefined && <p className="om-note om-tone-warn" role="status">Only an owner can make a join code. You can look at the network.</p>}
      <NetworkPage mesh={m} fabric={f} now={hub.now} isOwner={isOwner} onAddDevice={() => setAdding(true)}
        onReviewJoin={(id) => navigate(href.approval(id))} onRetry={reload} />
      <Card title="Box certificate" level={2}>
        {tls.data ? (
          <>
            <p>Your phone or a new machine must trust this box's own certificate authority before it can open the box over HTTPS. Check that its fingerprint matches before you install it.</p>
            <p><code title={tls.data.ca_sha256}>{tls.data.ca_sha256}</code></p>
            <p>
              <a className="om-btn om-btn-primary" href={api.caCertUrl?.('der')} download>Download certificate (.crt)</a>{' '}
              <a href={api.caCertUrl?.('pem')} download="onemind-ca.pem">Download as PEM text</a>
            </p>
          </>
        ) : tls.error ? (
          <p className="om-note om-tone-bad" role="status">Could not read the certificate: {tls.error.message}</p>
        ) : (
          <p aria-busy="true">Reading the certificate…</p>
        )}
      </Card>
      {isOwner && (
        <AddDevice open={adding} onClose={() => { setAdding(false); reload(); }} mode={mesh.data?.mode ?? 'lan'} now={hub.now}
          fabric={fabric.data ?? null} createTicket={(role) => (api.createJoinTicket as NonNullable<typeof api.createJoinTicket>)(role)}
          onReview={(id) => { setAdding(false); navigate(href.approval(id)); }} />
      )}
    </>
  );
}
