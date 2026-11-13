// SPDX-License-Identifier: Apache-2.0
// One machine in the fabric. Shapes follow contract §2 (heartbeat) and §3 (status, last_seen).
// A stale or offline node keeps its last values but says so, and never looks live.
import type { ReactNode } from 'react';
import { formatAgo, secondsSince } from '../lib/time';
import { freshness, type Freshness } from '../lib/freshness';
import { Card } from './Card';
import { FreshnessPill, StatusPill } from './StatusPill';
import { Meter } from './Meter';

export interface NodeSummary {
  node_id: string;
  hostname: string;
  role: 'hub' | 'node';
  board: string;
  arch: string;
  os: { pretty: string };
  cpus: number;
  mem_total_mb: number;
  mem_available_mb: number;
  disk_total_gb: number;
  disk_free_gb: number;
  k3s: { present: boolean; ready: boolean; role?: string | null };
  rauc: { present: boolean; booted_slot: string | null };
  gpu?: { nvidia: boolean; model: string | null };
  last_seen: string;
  /** Gateway's verdict (§3). When absent the card computes it from last_seen. */
  status?: 'online' | 'stale' | 'offline';
  /** Installed app count, if known. */
  apps?: number;
}

const BOARD: Record<string, string> = {
  'x86_64-efi': 'x86-64 PC',
  'arm64-efi': 'ARM64 PC',
  rpi5: 'Raspberry Pi 5',
  'jetson-orin': 'Jetson Orin',
  vm: 'Virtual machine',
  'vm-do': 'Cloud VM',
  unknown: 'Unknown board',
};

const STATUS_TO_FRESH: Record<NonNullable<NodeSummary['status']>, Freshness> = { online: 'live', stale: 'stale', offline: 'offline' };

export function NodeCard({ node, now, actions }: { node: NodeSummary; now: number; actions?: ReactNode }) {
  const age = secondsSince(node.last_seen, now);
  const state = node.status ? STATUS_TO_FRESH[node.status] : freshness(age);
  const notLive = state !== 'live';
  const memUsed = (node.mem_total_mb - node.mem_available_mb) / 1024;
  const diskUsed = node.disk_total_gb - node.disk_free_gb;
  return (
    <Card
      as="article"
      level={3}
      variant={notLive ? 'stale' : 'default'}
      title={node.hostname}
      subtitle={`${node.role === 'hub' ? 'Hub' : 'Node'} · ${BOARD[node.board] ?? node.board} · ${node.arch}`}
      aside={<FreshnessPill state={state} detail={notLive ? `last seen ${formatAgo(age)}` : undefined} />}
      footer={actions}
    >
      {notLive && (
        <p className="om-note om-tone-warn">
          The values below are its last report from {formatAgo(age)}, not live.
        </p>
      )}
      <div className="om-node-meters">
        <Meter
          label="Memory"
          value={memUsed}
          max={node.mem_total_mb / 1024}
          valueText={`${memUsed.toFixed(1)} of ${(node.mem_total_mb / 1024).toFixed(1)} GB used`}
          stale={notLive}
        />
        <Meter
          label="Disk"
          value={diskUsed}
          max={node.disk_total_gb}
          valueText={`${node.disk_free_gb.toFixed(0)} GB free of ${node.disk_total_gb.toFixed(0)} GB`}
          stale={notLive}
        />
      </div>
      <dl className="om-facts">
        <div>
          <dt>System</dt>
          <dd>{node.os.pretty}</dd>
        </div>
        <div>
          <dt>Cluster</dt>
          <dd>{node.k3s.present ? (node.k3s.ready ? `k3s ${node.k3s.role ?? ''} ready` : 'k3s not ready') : 'not joined'}</dd>
        </div>
        <div>
          <dt>OS slot</dt>
          <dd>{node.rauc.present ? `booted ${node.rauc.booted_slot ?? '?'}` : 'no A/B (developer install)'}</dd>
        </div>
        <div>
          <dt>CPU</dt>
          <dd>
            {node.cpus} cores{node.gpu?.nvidia ? ` · ${node.gpu.model ?? 'NVIDIA GPU'}` : ''}
          </dd>
        </div>
        {node.apps !== undefined && (
          <div>
            <dt>Apps</dt>
            <dd>{node.apps}</dd>
          </div>
        )}
      </dl>
      {node.k3s.present && !node.k3s.ready && !notLive && <StatusPill tone="warn" label="Cluster agent not ready" />}
    </Card>
  );
}
