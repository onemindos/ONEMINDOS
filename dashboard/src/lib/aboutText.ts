// SPDX-License-Identifier: Apache-2.0
// The "Copy details" text of Settings, About this box (UMB-P14, #432). It lists only the fields named
// below, so nothing the hub might send beyond them (a serial number, an address) can reach the clipboard.
// The node id is the one stable identifier left; it is printed only when the owner turns it on.
import type { AboutBox } from '../api/client';

type Node = AboutBox['nodes'][number];

const dash = (v: string | null | undefined) => (v ? v.replace(/\p{Cc}/gu, ' ') : '-');

export function uptimeText(s: number | null | undefined): string {
  if (s == null) return '-';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d}d ${h}h` : `${h}h ${m}m`;
}

export const memText = (mb: number | null | undefined) => (mb == null ? '-' : `${(mb / 1024).toFixed(1)} GB`);
export const diskText = (gb: number | null | undefined) => (gb == null ? '-' : `${Math.round(gb)} GB`);

/** The labelled facts of one node, in the order the screen and the copied text show them. */
export function nodeFacts(n: Node): Array<[string, string]> {
  return [
    ['Hostname', dash(n.hostname)],
    ['Board', dash(n.board)],
    ['OneMind', dash(n.onemind_version)],
    ['A/B slot', dash(n.booted_slot)],
    ['OS', dash(n.os_pretty)],
    ['Kernel', dash(n.kernel)],
    ['CPU', n.cpu_model ? `${dash(n.cpu_model)}${n.cpus ? ` (${n.cpus} cores)` : ''}` : '-'],
    ['Memory', memText(n.mem_total_mb)],
    ['Disk', `${diskText(n.disk_total_gb)} (${diskText(n.disk_free_gb)} free)`],
    ['Uptime', uptimeText(n.uptime_s)],
  ];
}

export function aboutText(about: AboutBox, includeNodeId: boolean): string {
  const lines = [`OneMind support details (${about.node_count} node${about.node_count === 1 ? '' : 's'})`];
  for (const n of about.nodes) {
    lines.push('');
    if (includeNodeId) lines.push(`Node ID: ${dash(n.node_id)}`);
    for (const [k, v] of nodeFacts(n)) lines.push(`${k}: ${v}`);
  }
  return lines.join('\n') + '\n';
}
