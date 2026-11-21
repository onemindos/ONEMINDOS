// SPDX-License-Identifier: Apache-2.0
// Simple and Pro by role (report ch. 3, UX-1, UX-2): there is no global "Pro mode" switch. The
// Pro screens appear for the roles that run the box (owner, adult); guests and children see the
// simple set. The gateway still enforces every route by scope; this only decides what is offered.
import type { Me } from '../api/wiring';
import type { Principal } from '../api/types';

/** core/onemind_core/auth.py ROLES: owner, adult, guest, child, agent. */
export const PRO_ROLES: ReadonlySet<string> = new Set(['owner', 'adult']);

/** Nav ids (routes.ts navId) of the Pro screens: Nodes, Control Hub, AI & Agents, and System
 * (Storage, Backups, Automation, OS updates, Network, which is also owner-only: OWNER_SCREENS). */
export const PRO_SCREENS: ReadonlySet<string> = new Set(['nodes', 'control-hub', 'agents', 'storage', 'backups', 'automation', 'updates', 'network']);

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

/** Is this nav item shown to this view? Pro screens stay hidden until the role is known. */
export function showsNav(id: string, view: View, role?: string | null): boolean {
  if (OWNER_SCREENS.has(id) && role !== 'owner') return false;
  return !PRO_SCREENS.has(id) || view === 'pro';
}

/** Wait before retrying a failed GET /v1/me: 1 s, 2 s, 4 s, then every 30 s. */
export function meRetryDelay(attempt: number): number {
  return attempt < 3 ? 1000 * 2 ** attempt : 30_000;
}
