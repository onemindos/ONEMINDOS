// SPDX-License-Identifier: Apache-2.0
// Simple and Pro by role (report ch. 3, UX-1, UX-2): there is no global "Pro mode" switch. The
// Pro screens appear for the roles that run the box (owner, adult); guests, children and teens see the
// simple set. The gateway still enforces every route by scope; this only decides what is offered.
import type { Me } from '../api/wiring';
import type { Principal } from '../api/types';
import { PRO_SCREEN_IDS } from '../screens/registry';

/** core/onemind_core/auth.py ROLES: owner, adult, guest, child, teen, agent. */
export const PRO_ROLES: ReadonlySet<string> = new Set(['owner', 'adult']);

/** Nav ids of the Pro screens: every screen that declares `pro: true` in src/screens/<id>/screen.ts, plus Alerts (hidden from the Simple nav, but its route stays open: an agent may ask to fix). */
export const PRO_SCREENS: ReadonlySet<string> = new Set([...PRO_SCREEN_IDS, 'alerts']);

/** Screens a guest or child is not offered at all: they cannot decide anything, so no Approvals. */
export const SIMPLE_HIDDEN: ReadonlySet<string> = new Set(['approvals']);

/** Pro screens only an owner may open: the gateway answers 403 to everyone else (GET /v1/network). */
export const OWNER_SCREENS: ReadonlySet<string> = new Set(['network']);

export type View = 'pro' | 'simple' | 'unknown';

export function viewFor(role: string | null | undefined): View {
  if (role === undefined) return 'unknown';
  return role !== null && PRO_ROLES.has(role) ? 'pro' : 'simple';
}

/** The role from the session when it is known, else from GET /v1/me (an agent has no person role). */
export function roleOf(principal: Principal | undefined, me: Me | undefined): string | null | undefined {
  if (principal) return principal.role;
  if (!me) return undefined;
  return me.principal.kind === 'person' ? (me.principal.role ?? null) : me.principal.kind;
}

/**
 * A signed-in person whose role the gateway refuses to let decide: everyone but the owner. An agent
 * is not in this set: it can ask, and the gateway's refusal still switches its buttons off.
 */
export function cannotDecide(role: string | null | undefined): boolean {
  return typeof role === 'string' && role !== 'owner' && role !== 'agent';
}

/**
 * The one rule for who is offered Approve and Deny: the role overrides the hub's own answer, so Home,
 * Approvals and the palette cannot drift apart. 'unknown' stays 'unknown' until something decides.
 */
export function decideState(role: string | null | undefined, hub: 'yes' | 'no' | 'unknown'): 'yes' | 'no' | 'unknown' {
  return cannotDecide(role) ? 'no' : hub;
}

/** Is this nav item shown to this view? Pro screens stay hidden until the role is known. */
export function showsNav(id: string, view: View, role?: string | null): boolean {
  if (view === 'simple' && SIMPLE_HIDDEN.has(id)) return false;
  // Approvals is for the owner, who decides. Adults, teens, children and guests cannot, and the
  // role is not known yet in the 'unknown' view, so nothing is offered until it is.
  if (id === 'approvals' && (view === 'unknown' || cannotDecide(role))) return false;
  if (OWNER_SCREENS.has(id) && role !== 'owner') return false;
  return !PRO_SCREENS.has(id) || view === 'pro';
}

/** Wait before retrying a failed GET /v1/me: 1 s, 2 s, 4 s, then every 30 s. */
export function meRetryDelay(attempt: number): number {
  return attempt < 3 ? 1000 * 2 ** attempt : 30_000;
}
