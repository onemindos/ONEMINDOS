// SPDX-License-Identifier: Apache-2.0
// Demo of the Network page and Add a device (CORE-NET-13). Routes: #/network, #/network/add
// (the dialog open), #/network/stale, #/network/error. Fixtures only, frozen clock; mesh
// addresses are Headscale's default range and the join code is made up.
import { useState } from 'react';
import { AddDevice, NetworkPage, useToast, type FabricSummary, type JoinTicket, type Loadable, type MeshView } from '../../../src';

const NOW = Date.parse('2026-11-12T10:00:00Z');
const CA = '95f1b8a22931cd15fb071e7e6dd54293a9a0736101c4ad8a99801d3f35001376';

const mesh: MeshView = {
  mode: 'lan', box: 'box1', control: { state: 'up', checked_at: '2026-11-12T09:59:58Z' }, relay: null,
  nodes: [
    { node_id: '015b84f630a9', name: 'hub', role: 'hub', online: true, state: 'up', path: 'none', mesh_ip: '100.64.0.1' },
    { node_id: 'dddbafc5d447', name: 'node-dddbafc5d447', role: 'worker', online: true, state: 'up', path: 'direct', mesh_ip: '100.64.0.2' },
    { node_id: '7a1c09e2b4f3', name: 'node-7a1c09e2b4f3', role: 'leaf', online: true, state: 'up', path: 'relayed', mesh_ip: '100.64.0.3' },
  ],
  devices: [],
  names: { lan: ['onemind.local', 'box1.local'], mesh: ['hub.onemind.internal'] },
  apps: [
    { app_id: 'vaultwarden', lan: 'https://vaultwarden.box1.local', lan_alias: 'https://vaultwarden.onemind.local', mesh: 'https://vaultwarden.apps.onemind.internal' },
    { app_id: 'ntfy', lan: 'https://ntfy.box1.local', lan_alias: 'https://ntfy.onemind.local', mesh: 'https://ntfy.apps.onemind.internal' },
  ],
  https: true, ca_sha256: CA,
};

const fabric: FabricSummary = {
  hub_node_id: '015b84f630a9', counts: { hub: 1, worker: 1, leaf: 1 },
  nodes: [
    { node_id: 'dddbafc5d447', hostname: 'mini-pc', role: 'worker', state: 'online', leaf_link: 'up', mesh: { state: 'up', path: 'direct' }, cert_expires_at: '2027-11-12T10:00:00Z', joined_at: '2026-11-12T09:40:00Z' },
    { node_id: '7a1c09e2b4f3', hostname: 'garden-pi', role: 'leaf', state: 'stale', leaf_link: 'down', mesh: { state: 'up', path: 'relayed' }, cert_expires_at: '2027-11-12T10:00:00Z', joined_at: '2026-11-11T18:00:00Z' },
  ],
  joining: [
    { join_request_id: 'jr_01', node_id: '3f9c2a1b7d4e', hostname: 'pi5-office', role: 'worker', state: 'awaiting_approval', match_code: 'K7-4QX', action_id: '6f1c9e0a-0000-4000-8000-000000000001', created_at: '2026-11-12T09:58:30Z' },
  ],
};

function ticketFor(role: 'worker' | 'leaf'): JoinTicket {
  const code = '7KQ4-M2XP-9D3F';
  return {
    ticket_id: 'tkt_demo', role, expires_at: '2026-11-12T10:15:00Z', hub_ca_sha256: CA, hub_url: 'https://box1.local',
    qr_payload: `onemind-join:v1?code=${code}&ca=${CA}&role=${role}&hub=https%3A%2F%2Fbox1.local`,
    one_time: { join_code: code },
  };
}

export function NetworkDemo({ arg }: { arg?: string }) {
  const toast = useToast();
  const [open, setOpen] = useState(arg === 'add');
  const meshL: Loadable<MeshView> = arg === 'error' ? { state: 'error', message: 'unavailable (mesh_control_down)' }
    : arg === 'stale' ? { state: 'ok', data: mesh, staleSince: '2026-11-12T09:48:00Z' } : { state: 'ok', data: mesh };
  const review = (id: string) => toast.show({ tone: 'info', title: 'Opens the approval card', body: `Approvals → node.join ${id.slice(0, 8)}…` });
  return (
    <>
      <NetworkPage mesh={meshL} fabric={{ state: 'ok', data: fabric }} now={NOW} isOwner onAddDevice={() => setOpen(true)}
        onReviewJoin={review} onRetry={() => toast.show({ tone: 'info', title: 'Retrying' })} />
      <AddDevice open={open} onClose={() => setOpen(false)} mode="lan" now={NOW} fabric={fabric}
        createTicket={async (role) => ticketFor(role)} onReview={review} />
    </>
  );
}
