// SPDX-License-Identifier: Apache-2.0
// Words for a standing approval ("rule"), written from the gateway's own fields (ApprovalPolicy).
import type { OneMind, components } from '@onemind/sdk';
import { modeLabel } from '../../lib/permissions';

export type Rule = components['schemas']['ApprovalPolicy'];
export type AuditRecord = components['schemas']['AuditRecord'];

const who = (name: string) => name.replace(/^(agent|person|plugin|automation):/, '');

/** "notes-helper may app.restart (app_id = notes)". */
export function ruleLine(r: Rule): string {
  const pins = Object.entries(r.allow.params ?? {}).map(([k, c]) => `${k} = ${String((c as { const?: unknown }).const ?? 'limited')}`);
  return `${r.allow.requested_by.map(who).join(', ')} may ${r.allow.types.join(', ')}${pins.length ? ` (${pins.join(', ')})` : ''}`;
}

export const day = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '');

export function lifetime(r: Rule): string {
  const end = r.forever ? 'No end date' : `Ends ${day(r.expires_at)}`;
  return r.lapse_unused_days ? `${end} · ends early if unused for ${r.lapse_unused_days} days` : end;
}

export function limitsLine(r: Rule): string {
  const parts = [`up to ${r.limits.per_day} a day`];
  if (r.limits.max_uses) parts.push(`${r.limits.max_uses} uses in total`);
  if (r.limits.items_per_day) parts.push(`${r.limits.items_per_day} items a day`);
  if (r.limits.bytes_per_day) parts.push(`${Math.round(r.limits.bytes_per_day / 1024)} KB a day`);
  return parts.join(' · ');
}

export function usesLine(r: Rule): string {
  if (!r.uses) return 'Not used yet';
  return `Used ${r.uses} ${r.uses === 1 ? 'time' : 'times'} (${r.uses_24h} in the last 24 hours)${r.last_used_at ? `, last on ${day(r.last_used_at)}` : ''}`;
}

export const NOTIFY: Record<string, string> = {
  each: 'You get a notice every time it is used',
  digest: 'Uses are listed in your daily summary',
  silent: 'No notices (read-only rules only)',
};

/** Why a live rule does nothing right now, or undefined. */
export function idleReason(r: Rule): string | undefined {
  const off = Object.entries(r.modes ?? {}).filter(([, m]) => m === 'locked' || m === 'ask');
  if (!off.length) return undefined;
  return `Not in use: ${off.map(([n, m]) => `${who(n)} is on ${modeLabel(m)}`).join(', ')}, which ignores rules.`;
}

export const live = (r: Rule) => ['active', 'suspended', 'paused'].includes(r.state);

const SUSPENDED: Record<string, string> = {
  token_rotated: 'its key was replaced',
  token_reminted: 'it was given a second key',
  token_revoked: 'its key was revoked',
  became_exposed: 'it started reading outside text',
  owner_role_changed: 'its owner’s role changed',
  risk_raised: 'what it asks for became riskier',
  push_failed: 'a notice about it could not be delivered',
  no_push_target: 'there is no phone to send its notices to',
};
export const suspendedWhy = (reason?: string | null) => (reason ? SUSPENDED[reason] ?? reason.replace(/_/g, ' ') : 'something about it changed');

/** The rule's history (created, every revision, suspension, re-confirm, revoke) from the audit log. */
export async function history(sdk: OneMind, r: Rule): Promise<AuditRecord[]> {
  const since = new Date(Date.parse(r.created_at) - 1000).toISOString();
  const out: AuditRecord[] = [];
  let after: number | undefined;
  for (let page = 0; page < 5; page++) {
    const { records, more } = await sdk.audit.list({ event: 'automation.policy.created,approval.policy.*', since, afterSeq: after, limit: 500 });
    out.push(...records.filter((x) => (x.data as { policy_id?: string } | null)?.policy_id === r.id));
    if (!more || !records.length) break;
    after = records[records.length - 1]!.seq;
  }
  return out;
}

const EVENT: Record<string, string> = {
  'automation.policy.created': 'Created',
  'approval.policy.revised': 'Changed',
  'approval.policy.revoked': 'Revoked',
  'approval.policy.suspended': 'Suspended',
  'approval.policy.paused': 'Paused',
  'approval.policy.reconfirmed': 'Re-confirmed',
  'approval.policy.kept': 'Kept at its review',
  'approval.policy.lapsed': 'Ended: unused',
  'approval.policy.bound': 'Bound to its agent',
};

export function historyLine(x: AuditRecord): string {
  const d = (x.data ?? {}) as { revision?: number; direction?: string; changed?: string[]; reason?: string };
  const what = EVENT[x.event] ?? x.event;
  const by = x.principal && typeof x.principal === 'object' && 'id' in x.principal ? ` by ${String((x.principal as { id: unknown }).id)}` : '';
  const rev = d.revision ? ` (revision ${d.revision})` : '';
  const detail = d.changed?.length ? `: ${d.direction === 'widen' ? 'widened' : 'narrowed'} ${d.changed.join(', ')}` : d.reason ? `: ${suspendedWhy(d.reason)}` : '';
  return `${what}${rev}${detail}${by}`;
}
