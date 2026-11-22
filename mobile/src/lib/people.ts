// SPDX-License-Identifier: Apache-2.0
// People and agents (FAM-01, CORE-SEC-6): pure helpers. The phone shows who may do what and files what an
// owner asks for; the hub decides and enforces (every role limit and every refusal is the hub's).
import type { Action, FamilyProfile, TokenInfo } from '../api/types';

/** Roles an owner can give a person, most to least trusted. `teen` is FAM-01 (founder, 2026-11-21). */
export const ROLES = ['owner', 'adult', 'teen', 'child', 'guest'] as const;
export type Role = (typeof ROLES)[number];

export const ROLE_TEXT: Record<Role, string> = {
  owner: 'Runs the box and approves every change.',
  adult: 'Uses the apps shared with them and can ask for changes.',
  teen: 'Uses apps within their limits. Asks a parent for anything else.',
  child: 'Uses only the apps a parent allows. Asks a parent for anything else.',
  guest: 'Sees only what is shared with them.',
};

export function roleLabel(role: string): string {
  return (ROLES as readonly string[]).includes(role) ? role[0]!.toUpperCase() + role.slice(1) : `Unknown (${role})`;
}

/** Roles that carry per-person limits and cannot approve anything: they ask a parent. */
export function asksParent(role: string | undefined): boolean {
  return role === 'teen' || role === 'child';
}

/** One plain line for a person's limits; the owner edits them on the dashboard. */
export function limitsText(p: FamilyProfile | undefined): string {
  if (!p) return 'No limits set.';
  const parts: string[] = [];
  if (p.max_age_rating != null) parts.push(`apps rated above ${p.max_age_rating} are hidden`);
  if (p.allowed_apps) parts.push(p.allowed_apps.length === 0 ? 'no apps allowed' : `${p.allowed_apps.length} allowed app${p.allowed_apps.length === 1 ? '' : 's'}`);
  if (p.blocked_tags && p.blocked_tags.length > 0) parts.push(`blocked: ${p.blocked_tags.join(', ')}`);
  if (p.windows) parts.push(p.windows.length === 0 ? 'no allowed hours' : 'allowed hours set');
  return parts.length ? parts.join('; ') + '.' : 'No limits set.';
}

export interface AgentSummary {
  id: string;
  asks: number;
  waiting: number;
  approved: number;
  denied: number;
  last?: string;
  scopes: string[] | undefined;
  recent: Action[];
}

/** Agents seen in the action list (what they asked) joined with their tokens (what they may do). */
export function summarizeAgents(actions: Action[], tokens: TokenInfo[] | undefined): AgentSummary[] {
  const by = new Map<string, AgentSummary>();
  const get = (id: string) => {
    let a = by.get(id);
    if (!a) by.set(id, (a = { id, asks: 0, waiting: 0, approved: 0, denied: 0, scopes: undefined, recent: [] }));
    return a;
  };
  for (const t of tokens ?? []) if (t.kind === 'agent') get(t.principal_id).scopes = [...new Set([...(get(t.principal_id).scopes ?? []), ...t.scopes])].sort();
  for (const a of actions) {
    if (a.requested_by?.kind !== 'agent') continue;
    const s = get(a.requested_by.id);
    s.asks += 1;
    if (a.state === 'awaiting_approval' || a.state === 'requested') s.waiting += 1;
    else if (a.state === 'cancelled' && a.decided_by) s.denied += 1;
    else if (a.state === 'succeeded' || a.state === 'accepted' || a.state === 'dispatched') s.approved += 1;
    const at = a.created_at ?? a.updated_at;
    if (at && (!s.last || at > s.last)) s.last = at;
    s.recent.push(a);
  }
  for (const s of by.values()) s.recent = s.recent.sort((x, y) => (y.created_at ?? '').localeCompare(x.created_at ?? '')).slice(0, 3);
  return [...by.values()].sort((a, b) => (b.last ?? '').localeCompare(a.last ?? '') || a.id.localeCompare(b.id));
}
