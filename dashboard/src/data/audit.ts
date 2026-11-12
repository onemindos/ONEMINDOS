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
