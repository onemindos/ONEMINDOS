// SPDX-License-Identifier: Apache-2.0
// Data shapes of the networking screens, one per gateway response (routers/net.py):
// GET /v1/mesh, GET /v1/fabric, POST /v1/fabric/join-tickets (contract §12.11; NETWORKING.md §15).

export type ReachMode = 'lan' | 'relay' | 'direct' | 'hosted' | 'off';
export type Role = 'hub' | 'worker' | 'leaf';
export type Path = 'direct' | 'relayed' | 'none';

export interface MeshNode {
  node_id: string | null;
  name: string;
  role: Role;
  online: boolean;
  state: 'up' | 'down' | 'none';
  path: Path;
  /** Only with ?addresses=1, for the owner; never shown by default (contract §2). */
  mesh_ip?: string;
}

export interface MeshDevice {
  id: string;
  label: string;
  online: boolean;
  mesh_ip?: string;
}

export interface AppLink {
  app_id: string;
  /** https://<app>.<box>.local */
  lan: string;
  /** https://<app>.onemind.local */
  lan_alias: string;
  /** https://<app>.apps.onemind.internal (over the mesh, away from home) */
  mesh: string;
}

export interface MeshView {
  mode: ReachMode;
  box: string;
  control: { state: 'up' | 'down' | 'off'; checked_at: string | null };
  relay: null | { state: string; checked_at: string | null };
  nodes: MeshNode[];
  devices: MeshDevice[];
  names: { lan: string[]; mesh: string[] };
  apps: AppLink[];
  https: boolean;
  ca_sha256: string;
}

export interface FabricNode {
  node_id: string;
  hostname: string;
  role: 'worker' | 'leaf';
  /** joining, or the heartbeat status once joined: online | stale | offline */
  state: string;
  leaf_link: 'up' | 'down' | 'none';
  mesh: { state: string; path: Path } | null;
  cert_expires_at: string | null;
  joined_at: string | null;
}

export interface JoinRequest {
  join_request_id: string;
  node_id: string;
  hostname: string;
  role: 'worker' | 'leaf';
  state: 'awaiting_approval' | 'approved' | 'delivering' | 'delivered';
  match_code: string;
  action_id: string;
  created_at: string;
}

export interface FabricSummary {
  hub_node_id: string | null;
  counts: Record<string, number>;
  nodes: FabricNode[];
  joining: JoinRequest[];
}

export interface JoinTicket {
  ticket_id: string;
  role: 'worker' | 'leaf';
  expires_at: string;
  hub_ca_sha256: string;
  hub_url: string;
  qr_payload: string;
  one_time: { join_code: string };
}

/** How a panel receives data: honest loading, error and stale states (PRINCIPLES P2). */
export type Loadable<T> =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ok'; data: T; staleSince?: string };
