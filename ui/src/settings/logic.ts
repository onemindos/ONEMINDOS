// SPDX-License-Identifier: Apache-2.0
// Pure rules behind the Settings, Activity and Approvals screens. No React, no clock of its
// own: every function that judges age takes `now` (the hub's clock) from the caller.
import type { Tone } from '../tokens/tokens';
import { formatAgo, secondsSince } from '../lib/time';
import { CATEGORY_LABEL, DEPLOY_ORDER, type CategorySlug, type DeployClass } from './taxonomy';
import type { ActionPlan, ApiToken, AuditEntry, AuditVerify, Effect, EffectKind, GatewayError, Loadable } from './types';

const DAY = 86_400;

/** A badge: one word with a tone, plus a sentence. Colour is never the only signal. */
export interface Badge {
  tone: Tone;
  label: string;
  detail: string;
}

/**
 * Last verified restore (BACKUPS, BAK-B1). A backup that was never restored is a hope, not a
 * backup: within 7 days is good, within 30 is a warning, older or never is bad.
 */
export function restoreBadge(last: { at: string; result: 'ok' | 'failed' } | null, now: number): Badge {
  if (!last) return { tone: 'bad', label: 'Never verified', detail: 'No restore has been tested yet.' };
  const s = secondsSince(last.at, now);
  if (!Number.isFinite(s)) return { tone: 'warn', label: 'Unknown', detail: 'The restore date could not be read.' };
  if (last.result === 'failed') return { tone: 'bad', label: 'Restore test failed', detail: `Last test ${formatAgo(s)}.` };
  if (s <= 7 * DAY) return { tone: 'ok', label: 'Restore verified', detail: `Tested ${formatAgo(s)}.` };
  if (s <= 30 * DAY) return { tone: 'warn', label: 'Verify soon', detail: `Last tested ${formatAgo(s)}.` };
  return { tone: 'bad', label: 'Restore not verified', detail: `Last tested ${formatAgo(s)}.` };
}

/** "Chain verified" banner (SECURITY §3.7). A check older than a day is reported as stale. */
export function chainBadge(v: AuditVerify, now: number): Badge {
  const age = secondsSince(v.checked_at, now);
  const when = formatAgo(age);
  const span = `entries #${v.first.toLocaleString('en-US')} to #${v.last.toLocaleString('en-US')}`;
  if (v.state === 'checking') return { tone: 'info', label: 'Checking the chain', detail: `Reading ${span}.` };
  if (v.state === 'broken')
    return { tone: 'bad', label: 'Chain broken', detail: `Entry #${v.broken_at ?? '?'} does not match the one before it. Checked ${when}. An alert was raised.` };
  if (!Number.isFinite(age) || age > DAY) return { tone: 'warn', label: 'Chain check is old', detail: `Last verified ${when} (${span}). Run a new check.` };
  return { tone: 'ok', label: 'Chain verified', detail: `${span}, checked ${when}. No gaps, no edits.` };
}

export type TokenState = 'active' | 'expiring' | 'expired' | 'revoked';
/** Token lifecycle (SECURITY §3.3): expiring = less than 7 days left. */
export function tokenState(t: Pick<ApiToken, 'expires_at' | 'revoked_at'>, now: number): TokenState {
  if (t.revoked_at) return 'revoked';
  if (!t.expires_at) return 'active';
  const left = (Date.parse(t.expires_at) - now) / 1000;
  if (!Number.isFinite(left) || left <= 0) return 'expired';
  return left < 7 * DAY ? 'expiring' : 'active';
}
export const TOKEN_STATE: Record<TokenState, { tone: Tone; label: string }> = {
  active: { tone: 'ok', label: 'Active' },
  expiring: { tone: 'warn', label: 'Expires soon' },
  expired: { tone: 'neutral', label: 'Expired' },
  revoked: { tone: 'neutral', label: 'Revoked' },
};

/** Minutes since midnight for "HH:MM"; NaN when unreadable. */
export function minutesOf(hhmm: string): number {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm);
  if (!m) return Number.NaN;
  const h = Number(m[1]);
  const min = Number(m[2]);
  return h < 24 && min < 60 ? h * 60 + min : Number.NaN;
}

/** Whether quiet hours cover `minute` (0–1439). Handles windows that cross midnight. */
export function inQuietHours(q: { enabled: boolean; start: string; end: string }, minute: number): boolean {
  if (!q.enabled) return false;
  const s = minutesOf(q.start);
  const e = minutesOf(q.end);
  if (!Number.isFinite(s) || !Number.isFinite(e) || s === e) return false;
  return s < e ? minute >= s && minute < e : minute >= s || minute < e;
}

/* ---------- effects card ---------- */

/** Plain-language groups for the effects card, in reading order. */
export const EFFECT_GROUPS: Array<{ title: string; kinds: EffectKind[] }> = [
  { title: 'Deletes', kinds: ['data-delete'] },
  { title: 'Reachable from', kinds: ['exposure', 'port', 'host-network'] },
  { title: 'Gives agents', kinds: ['agent-scope'] },
  { title: 'Uses hardware', kinds: ['device'] },
  { title: 'Talks to', kinds: ['egress'] },
  { title: 'Stores', kinds: ['volume', 'secret'] },
  { title: 'Downloads', kinds: ['image'] },
  { title: 'Interrupts', kinds: ['restart'] },
];
const RISK_RANK = { low: 0, medium: 1, high: 2 } as const;
export const RISK: Record<Effect['risk'], { tone: Tone; label: string }> = {
  low: { tone: 'ok', label: 'Low impact' },
  medium: { tone: 'warn', label: 'Check before approving' },
  high: { tone: 'bad', label: 'High impact' },
};

/** Effects grouped for reading, empty groups dropped, the riskiest effect first in each group. */
export function groupEffects(effects: Effect[]): Array<{ title: string; items: Effect[] }> {
  return EFFECT_GROUPS.map((g) => ({
    title: g.title,
    items: effects.filter((e) => g.kinds.includes(e.kind)).sort((a, b) => RISK_RANK[b.risk] - RISK_RANK[a.risk]),
  })).filter((g) => g.items.length > 0);
}

/** The highest risk in a plan. A one-way action is at least medium; a stale placement too. */
export function planRisk(p: Pick<ActionPlan, 'effects' | 'undo' | 'placement'>): Effect['risk'] {
  let r = p.effects.reduce<Effect['risk']>((acc, e) => (RISK_RANK[e.risk] > RISK_RANK[acc] ? e.risk : acc), 'low');
  if ((p.undo === 'one-way' || p.placement?.stale || p.placement?.fits === false) && r === 'low') r = 'medium';
  return r;
}

export const UNDO_TEXT: Record<ActionPlan['undo'], string> = {
  reversible: 'Can be undone with one request.',
  snapshot: 'A snapshot is taken first; it is reverted automatically if health checks fail.',
  'one-way': 'Cannot be undone.',
};

/* ---------- activity timeline ---------- */

export type ActorFilter = 'all' | 'person' | 'agent' | 'system';
export function filterAudit(entries: AuditEntry[], actor: ActorFilter, query = ''): AuditEntry[] {
  const q = query.trim().toLowerCase();
  return entries.filter((e) => {
    if (actor !== 'all') {
      const kind = e.actor.kind === 'device' ? 'system' : e.actor.kind;
      if (kind !== actor) return false;
    }
    if (!q) return true;
    return [e.text, e.actor.id, e.app, e.node, `#${e.seq}`].some((s) => s?.toLowerCase().includes(q));
  });
}

/** Newest first, split by UTC day so every viewer sees the hub's dates. */
export function groupByDay(entries: AuditEntry[], now: number): Array<{ key: string; label: string; items: AuditEntry[] }> {
  const dayKey = (iso: string) => new Date(Date.parse(iso)).toISOString().slice(0, 10);
  const today = new Date(now).toISOString().slice(0, 10);
  const yesterday = new Date(now - DAY * 1000).toISOString().slice(0, 10);
  const out: Array<{ key: string; label: string; items: AuditEntry[] }> = [];
  for (const e of [...entries].sort((a, b) => b.seq - a.seq)) {
    if (Number.isNaN(Date.parse(e.at))) continue;
    const key = dayKey(e.at);
    let g = out.find((x) => x.key === key);
    if (!g) {
      const label =
        key === today
          ? 'Today'
          : key === yesterday
            ? 'Yesterday'
            : new Date(`${key}T00:00:00Z`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short', timeZone: 'UTC' });
      g = { key, label, items: [] };
      out.push(g);
    }
    g.items.push(e);
  }
  return out;
}

/* ---------- categories and classes ---------- */

/** Usage per category, largest first; categories past `top` are folded into "Everything else". */
export function usageByCategory(apps: Array<{ category: CategorySlug; used_gb: number }>, top = 4): Array<{ key: string; label: string; gb: number }> {
  const sums = new Map<CategorySlug, number>();
  for (const a of apps) sums.set(a.category, (sums.get(a.category) ?? 0) + Math.max(0, a.used_gb));
  const sorted = [...sums.entries()].sort((a, b) => b[1] - a[1]);
  const head = sorted.slice(0, top).map(([k, gb]) => ({ key: k as string, label: CATEGORY_LABEL[k], gb }));
  const rest = sorted.slice(top).reduce((n, [, gb]) => n + gb, 0);
  return rest > 0 ? [...head, { key: 'rest', label: 'Everything else', gb: rest }] : head;
}

/** Group items by deployment class in DEPLOY_ORDER, empty classes dropped. */
export function byDeployClass<T extends { deploy_class: DeployClass }>(items: T[]): Array<{ cls: DeployClass; items: T[] }> {
  return DEPLOY_ORDER.map((cls) => ({ cls, items: items.filter((i) => i.deploy_class === cls) })).filter((g) => g.items.length > 0);
}

/* ---------- async state ---------- */

/** "12.4 GB" / "1.2 TB". */
export function formatGb(gb: number): string {
  if (!Number.isFinite(gb)) return 'unknown';
  return gb >= 1000 ? `${(gb / 1000).toFixed(1)} TB` : gb >= 10 ? `${Math.round(gb)} GB` : `${gb.toFixed(1)} GB`;
}

/** What to say for a gateway error; the code is always shown too (IA §4). */
export function errorText(e: GatewayError): string {
  switch (e.error) {
    case 'unavailable':
      return 'The hub is not answering. Nothing was changed.';
    case 'permission_denied':
      return 'Your account cannot see this. Ask the owner.';
    case 'unauthenticated':
      return 'Your session ended. Sign in again.';
    default:
      return e.message;
  }
}

/** Map the data of a ready Loadable; other states pass through unchanged. */
export function mapLoadable<T, U>(l: Loadable<T>, f: (t: T) => U): Loadable<U> {
  return l.status === 'ready' ? { ...l, data: f(l.data) } : l;
}

/** Search across a section's label and keywords. */
export function matchSection(s: { label: string; keywords?: string[] }, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [s.label, ...(s.keywords ?? [])].some((w) => w.toLowerCase().includes(q));
}
