// SPDX-License-Identifier: Apache-2.0
// What an app's page reads from the gateway (FD-06). The SDK types these bodies as `unknown`, so
// each is checked here and a malformed body is an error the page shows, never a guessed value.
// Paths are the SDK's generated route templates (`keyof paths`), filled in with the app id.
import { OneMind, OneMindError, type paths } from '@onemind/sdk';
import { ApiError } from '../api/types';

type Route = keyof paths;
type Rec = Record<string, unknown>;

/** Fill a generated route template, e.g. `/v1/apps/{app_id}/metrics`. */
export function route<R extends Route>(template: R, params: Record<string, string>, query?: Record<string, string>): string {
  const path = (template as string).replace(/\{(\w+)\}/g, (_, k: string) => encodeURIComponent(params[k] ?? ''));
  const q = query ? new URLSearchParams(query).toString() : '';
  return q ? `${path}?${q}` : path;
}

async function get(sdk: OneMind, path: string): Promise<unknown> {
  try { return await sdk.call<unknown>({ method: 'GET', path }); }
  catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}
const bad = (what: string) => new Error(`The hub returned an invalid ${what}.`);
const rec = (v: unknown, what: string): Rec => { if (!v || typeof v !== 'object' || Array.isArray(v)) throw bad(what); return v as Rec; };
const arr = (v: unknown, what: string): unknown[] => { if (!Array.isArray(v)) throw bad(what); return v; };
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

export interface Component { name: string; ready: boolean; restarts: number; lastExit: string | null; lastRestartAt: string | null }
export interface AppView {
  health: { state: string; reason: string | null };
  components: Component[];
  restarts: number;
  access: { roles: string[]; sharedWithMe: boolean } | null;
}
/** GET /v1/apps/{app_id}: health, components with restart counts, and who the app is shared with. */
export async function readAppView(sdk: OneMind, appId: string): Promise<AppView> {
  const b = rec(await get(sdk, route('/v1/apps/{app_id}', { app_id: appId })), 'app record');
  const h = rec(b.health, 'app health');
  if (typeof h.state !== 'string') throw bad('app health');
  const components = arr(b.components ?? [], 'component list').map((c) => {
    const r = rec(c, 'component');
    if (typeof r.name !== 'string' || typeof r.restarts !== 'number') throw bad('component');
    return { name: r.name, ready: r.ready === true, restarts: r.restarts, lastExit: str(r.last_exit_reason), lastRestartAt: str(r.last_restart_at) };
  });
  const a = b.access && typeof b.access === 'object' ? (b.access as Rec) : null;
  return {
    health: { state: h.state, reason: str(h.reason) },
    components,
    restarts: components.reduce((n, c) => n + c.restarts, 0),
    access: a && Array.isArray(a.roles) ? { roles: a.roles.filter((r): r is string => typeof r === 'string'), sharedWithMe: a.shared_with_me === true } : null,
  };
}

export interface Usage { components: Array<{ name: string; cpuMillicores: number | null; memMb: number | null }>; at: string | null; reason: string | null }
/** GET /v1/apps/{app_id}/metrics: CPU and memory per component; null (never 0) when not reported. */
export async function readUsage(sdk: OneMind, appId: string): Promise<Usage> {
  const b = rec(await get(sdk, route('/v1/apps/{app_id}/metrics', { app_id: appId })), 'usage record');
  return {
    at: str(b.at),
    reason: str(b.reason),
    components: arr(b.components, 'usage list').map((c) => {
      const r = rec(c, 'usage row');
      if (typeof r.name !== 'string') throw bad('usage row');
      return { name: r.name, cpuMillicores: num(r.cpu_millicores), memMb: num(r.mem_mb) };
    }),
  };
}

export interface Sharing { roles: string[]; people: Array<{ id: string; name: string }>; auth: string | null; allowed: boolean | null }
/** GET /v1/apps/{app_id}/access: an owner sees everyone; anyone else sees only their own part. */
export async function readSharing(sdk: OneMind, appId: string): Promise<Sharing> {
  const b = rec(await get(sdk, route('/v1/apps/{app_id}/access', { app_id: appId })), 'sharing record');
  return {
    roles: arr(b.roles, 'sharing roles').filter((r): r is string => typeof r === 'string'),
    people: arr(b.people ?? [], 'sharing people').map((p) => { const r = rec(p, 'person'); return { id: String(r.id ?? ''), name: str(r.display_name) ?? String(r.id ?? '') }; }),
    auth: str(b.auth),
    allowed: typeof b.allowed === 'boolean' ? b.allowed : null,
  };
}

export interface Snapshot { id: string; takenAt: string | null; reason: string | null; verifiedAt: string | null }
/** GET /v1/backups/snapshots?app_id=: this app's restore points, newest first. */
export async function readSnapshots(sdk: OneMind, appId: string): Promise<Snapshot[]> {
  const rows = arr(await get(sdk, route('/v1/backups/snapshots', {}, { app_id: appId })), 'snapshot list').map((s) => {
    const r = rec(s, 'snapshot');
    if (typeof r.id !== 'string') throw bad('snapshot');
    return { id: r.id, takenAt: str(r.taken_at), reason: str(r.reason), verifiedAt: str(r.verified_at) };
  });
  return rows.sort((a, b) => (b.takenAt ?? '').localeCompare(a.takenAt ?? ''));
}

/** The page's own path. The gateway already links its app notifications to `/apps/<id>`. */
export const appPageHref = (id: string) => `/apps/${encodeURIComponent(id)}`;
