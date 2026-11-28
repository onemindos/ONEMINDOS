// SPDX-License-Identifier: Apache-2.0
// The Atlas status strip (final design 01): how many machines are fresh, stale and offline, and a needs-you chip.
// Real data only: the counts come from GET /v1/nodes aged on the hub clock (hub.nodeStatus), the chip from the
// actions awaiting a decision. Before the first answer nothing is drawn: no zeros that look like a fact.
import { Icon } from '@onemind/ui';
import type { NodeStatus } from '../api/types';

export interface FleetCounts {
  fresh: number;
  stale: number;
  offline: number;
}

/** Count machines by state word: online is "fresh" (Atlas's word), stale and offline as they are. */
export function fleetCounts(statuses: readonly NodeStatus[]): FleetCounts {
  const c: FleetCounts = { fresh: 0, stale: 0, offline: 0 };
  for (const s of statuses) c[s === 'online' ? 'fresh' : s] += 1;
  return c;
}

/** "3 machines: 2 fresh, 1 stale, 0 offline" (the accessible summary). */
export function fleetSentence(c: FleetCounts): string {
  const n = c.fresh + c.stale + c.offline;
  return `${n} ${n === 1 ? 'machine' : 'machines'}: ${c.fresh} fresh, ${c.stale} stale, ${c.offline} offline`;
}

export function needsYouLabel(waiting: number): string {
  return waiting === 0 ? 'Nothing needs you' : `${waiting} ${waiting === 1 ? 'needs' : 'need'} you`;
}

export function FleetCountsView({ counts }: { counts: FleetCounts }) {
  return (
    <span className="dsk-fleet" title={fleetSentence(counts)}>
      <span className="om-visually-hidden">{fleetSentence(counts)}</span>
      {(['fresh', 'stale', 'offline'] as const).map((k) => (
        <span key={k} className={`dsk-fleet-item dsk-fleet-${k}`} aria-hidden="true">
          <span className="dsk-state-dot" />
          <b>{counts[k]}</b> {k}
        </span>
      ))}
    </span>
  );
}

export function NeedsYouChip({ waiting }: { waiting: number }) {
  return (
    <a href="/approvals" className="dsk-needchip" data-none={waiting === 0 || undefined} title="Open Approvals">
      {waiting === 0 ? <Icon name="check" size={14} /> : <span className="dsk-state-dot" aria-hidden="true" />}
      {needsYouLabel(waiting)}
    </a>
  );
}
