// SPDX-License-Identifier: Apache-2.0
// GET /v1/audit/events and /v1/audit/verify → the props of @onemind/ui AuditTimeline. Pure
// functions. The hub redacts audit data; this still shows only short scalar values, as text.
import type { ActivityData, AuditEntry, AuditVerify } from '@onemind/ui';
import type { AuditRecord, AuditVerifyResult } from '../api/wiring';

type Kind = AuditEntry['kind'];

export function auditKind(event: string): Kind {
  if (event.startsWith('auth.login') || event.startsWith('auth.logout') || event.startsWith('auth.setup') || event.startsWith('auth.session')) return 'sign-in';
  if (event === 'action.requested') return 'request';
  if (/^action\.(approved|denied|cancelled|expired)/.test(event)) return 'decision';
  if (event.startsWith('action.')) return 'result';
  if (event.includes('checkpoint')) return 'checkpoint';
  return 'config';
}

const PRINCIPAL_KINDS = ['person', 'agent', 'device', 'system'] as const;

function summary(data: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(data)) {
    if (parts.length >= 4) break;
    if (typeof v === 'string' && v.length <= 60) parts.push(`${k}: ${v}`);
    else if (typeof v === 'number' || typeof v === 'boolean') parts.push(`${k}: ${v}`);
  }
  return parts.join(', ');
}

export function toAuditEntry(r: AuditRecord): AuditEntry {
  const kind = PRINCIPAL_KINDS.find((k) => k === r.principal?.kind) ?? 'system';
  const role = r.principal?.role;
  const failed = /failed|denied|rejected|refused/.test(r.event);
  const s = summary(r.data);
  return {
    seq: r.seq,
    at: r.ts,
    actor: { id: r.principal?.id ?? 'system', kind, ...(role === 'owner' || role === 'adult' || role === 'guest' || role === 'agent' ? { role } : {}) },
    kind: auditKind(r.event),
    text: s ? `${r.event} (${s})` : r.event,
    result: failed ? 'bad' : 'info',
    hash: r.hash.slice(0, 8),
  };
}

export function toAuditVerify(v: AuditVerifyResult): AuditVerify {
  return {
    state: v.ok ? 'verified' : 'broken',
    first: 1,
    last: v.head?.seq ?? 0,
    checked_at: v.checked_at,
    ...(v.first_bad_seq != null ? { broken_at: v.first_bad_seq } : {}),
  };
}

/** Newest first, as the timeline reads best. */
export function toActivity(records: AuditRecord[], verify: AuditVerifyResult | undefined): ActivityData {
  return { ...(verify ? { verify: toAuditVerify(verify) } : {}), entries: [...records].sort((a, b) => b.seq - a.seq).map(toAuditEntry) };
}

/**
 * The AI & Agents view of the chain: records an agent wrote, plus every record about an action an
 * agent requested (the owner's decision and the executor's result), oldest first as the API sends.
 */
export function agentRecords(records: AuditRecord[]): AuditRecord[] {
  const agentActions = new Set(records.filter((r) => r.principal?.kind === 'agent' && r.action_id).map((r) => r.action_id!));
  return records.filter((r) => r.principal?.kind === 'agent' || (r.action_id !== null && agentActions.has(r.action_id)));
}

export interface AgentSummary {
  id: string;
  requests: number;
  approved: number;
  denied: number;
  last: string;
}

/** One row per agent: how often it asked, and how often a person said yes or no. */
export function agentSummaries(records: AuditRecord[]): AgentSummary[] {
  const byAction = new Map<string, string>();
  const rows = new Map<string, AgentSummary>();
  for (const r of records) {
    if (r.principal?.kind === 'agent') {
      const row = rows.get(r.principal.id) ?? { id: r.principal.id, requests: 0, approved: 0, denied: 0, last: r.ts };
      if (r.event === 'action.requested') row.requests += 1;
      if (r.ts > row.last) row.last = r.ts;
      rows.set(row.id, row);
      if (r.action_id) byAction.set(r.action_id, row.id);
    }
  }
  for (const r of records) {
    const agent = r.action_id ? byAction.get(r.action_id) : undefined;
    const row = agent ? rows.get(agent) : undefined;
    if (!row) continue;
    if (r.event === 'action.approved') row.approved += 1;
    if (r.event === 'action.denied') row.denied += 1;
  }
  return [...rows.values()].sort((a, b) => (a.last < b.last ? 1 : -1));
}
