// SPDX-License-Identifier: Apache-2.0
// Pure rules of the networking screens: QR matrix, ticket countdown, one row per machine.
import { encode } from 'uqr';
import type { FabricSummary, JoinTicket, MeshView, Path, Role } from './types';

/** QR modules (1 = dark) for text, error correction M, no quiet zone (the SVG adds it). */
export function qrModules(text: string): number[][] {
  return encode(text, { ecc: 'M', border: 0 }).data.map((row) => row.map((on) => (on ? 1 : 0)));
}

/** Whole seconds until iso, never negative. */
export function secondsLeft(iso: string, now: number): number {
  return Math.max(0, Math.floor((Date.parse(iso) - now) / 1000));
}

export function formatCountdown(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}

/** The two ways to use a ticket on the new machine. Quoted: the payload contains & and ?. */
export function joinCommands(t: Pick<JoinTicket, 'qr_payload'>): { install: string; joinOnly: string } {
  return {
    install: `sudo deploy/install.sh --role node --join '${t.qr_payload}'`,
    joinOnly: `sudo onemind fabric join '${t.qr_payload}'`,
  };
}

export const ROLE_LABEL: Record<Role, string> = { hub: 'Hub', worker: 'Worker', leaf: 'Leaf' };
export const ROLE_HELP: Record<'worker' | 'leaf', string> = {
  worker: 'Runs apps. Joins the cluster and the bus. For mini PCs, a Raspberry Pi 5 with 4 GB or more, a VM.',
  leaf: 'Reports and keeps working when the hub is away, runs no apps. For small or remote machines.',
};
export const PATH_LABEL: Record<Path, string> = { direct: 'Direct', relayed: 'Through the relay', none: 'Not connected' };

export interface MachineRow {
  key: string;
  name: string;
  role: Role;
  /** live | joining | offline | stale | down */
  status: 'online' | 'joining' | 'stale' | 'offline' | 'down';
  path: Path;
  leaf: 'up' | 'down' | 'none';
  meshIp?: string;
}

/** One row per machine: the hub and every fabric node, joined with what the mesh says. */
export function machineRows(mesh: MeshView, fabric: FabricSummary): MachineRow[] {
  const byId = new Map(mesh.nodes.filter((n) => n.node_id).map((n) => [n.node_id as string, n]));
  const hub = mesh.nodes.find((n) => n.role === 'hub');
  const rows: MachineRow[] = [
    {
      key: 'hub',
      name: mesh.box,
      role: 'hub',
      status: hub ? (hub.online ? 'online' : 'down') : mesh.mode === 'off' ? 'online' : 'down',
      path: 'none',
      leaf: 'none',
      meshIp: hub?.mesh_ip,
    },
  ];
  for (const n of fabric.nodes) {
    const m = byId.get(n.node_id);
    const status: MachineRow['status'] =
      n.state === 'joining' ? 'joining' : n.state === 'online' || n.state === 'stale' || n.state === 'offline' ? n.state : 'offline';
    rows.push({
      key: n.node_id,
      name: n.hostname,
      role: n.role,
      status,
      path: m?.path ?? n.mesh?.path ?? 'none',
      leaf: n.leaf_link,
      meshIp: m?.mesh_ip,
    });
  }
  return rows;
}

/** Requests the owner should look at: waiting for approval first, newest first. */
export function pendingJoins(fabric: FabricSummary) {
  return [...fabric.joining]
    .filter((j) => j.state === 'awaiting_approval')
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}
