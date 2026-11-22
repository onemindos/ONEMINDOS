// SPDX-License-Identifier: Apache-2.0
// What the phone sends and shows for the System screens. Same rule as lib/manage.ts: the phone only FILES a
// request (an owner approves it in Approvals); it never installs, restarts or shuts anything down itself.
import type { OneMindApi } from '../api/client';
import type { Action, NodeMetrics, NodeRecord, OsNodeUpdate, SystemControlType } from '../api/types';
import { REQUEST_TTL_MS } from './approvals';
import { uuidv4 } from './uuid';

/** The version a node could be asked to install: only when it reports an update service and an offer. */
export function installOffer(n: Pick<OsNodeUpdate, 'reported' | 'available_version' | 'current_version'>): string | undefined {
  return n.reported && n.available_version && n.available_version !== n.current_version ? n.available_version : undefined;
}

/** `os.update.install` (core/osupdate.py `InstallParams`): files a request, nothing installs until approved. */
export function requestOsInstall(api: OneMindApi, nodeId: string, version: string, now = Date.now()): Promise<Action> {
  return api.createAction({
    type: 'os.update.install',
    params: { node_id: nodeId, version },
    idempotency_key: uuidv4(),
    expires_at: new Date(now + REQUEST_TTL_MS).toISOString(),
  });
}

export const CONTROL_LABEL: Record<SystemControlType, string> = {
  'system.restart': 'Restart',
  'system.shutdown': 'Shut down',
  'system.troubleshoot': 'Troubleshoot',
};

/** File the control request bound to the plan that was shown (the hub answers 409 `plan_changed` otherwise). */
export function requestSystemControl(api: OneMindApi, type: SystemControlType, planSha256: string, now = Date.now()): Promise<Action> {
  return api.createAction({
    type,
    params: {},
    idempotency_key: uuidv4(),
    expires_at: new Date(now + REQUEST_TTL_MS).toISOString(),
    plan_sha256: planSha256,
  });
}

/** The newest sample that has any value, so a node that reports no CPU still shows memory and disk. */
export function latestSample(m: NodeMetrics | undefined): NodeMetrics['samples'][number] | undefined {
  return m?.samples.length ? m.samples[m.samples.length - 1] : undefined;
}

export const pct = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? 'not reported' : `${Math.round(v)}%`);

/** Used share of a total, as a whole percent; undefined when either number is missing or the total is zero. */
export function usedPct(used: number | null | undefined, total: number | null | undefined): number | undefined {
  if (used === null || used === undefined || total === null || total === undefined || !(total > 0)) return undefined;
  return Math.max(0, Math.min(100, (used / total) * 100));
}

/** The machine the hub runs on: the instance's hub node, else the first node with role hub, else the first. */
export function hubNode(nodes: NodeRecord[], hubId: string | null | undefined): NodeRecord | undefined {
  return nodes.find((n) => n.node_id === hubId) ?? nodes.find((n) => n.role === 'hub') ?? nodes[0];
}

export function uptimeText(s: number): string {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d} d ${h} h` : h > 0 ? `${h} h ${m} min` : `${m} min`;
}
