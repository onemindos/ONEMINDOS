// SPDX-License-Identifier: Apache-2.0
// Pure rules for the App Store: search and filters, the single primary action per app,
// request building with its API equivalent, and job progress. No React, fully unit-tested.
import { installBlockReason, safeHttpUrl, type AppTier } from '../lib/trust';
import { CATEGORIES, CATEGORY_BY_SLUG } from './taxonomy';
import type {
  Arch,
  CatalogApp,
  CategorySlug,
  DeployClass,
  JobState,
  LicenceClass,
  StoreActionRequest,
  StoreActionType,
  StoreJob,
} from './types';

// ---------------------------------------------------------------- search and filters

export interface MarketFilters {
  q: string;
  category: CategorySlug | null;
  tag: string | null;
  /** Deployment classes shown. Community is off by default (TAXONOMY §4.3). */
  classes: DeployClass[];
  /** "Runs on my nodes": hide apps the hub says no node can run (default on). */
  fitsOnly: boolean;
  arch: Arch | null;
  /** Empty means any licence class. */
  licences: LicenceClass[];
  tier: AppTier | 'any';
  pluginsOnly: boolean;
  noGpu: boolean;
}

export const DEFAULT_FILTERS: MarketFilters = {
  q: '',
  category: null,
  tag: null,
  classes: ['market-verified', 'list-only', 'private'],
  fitsOnly: true,
  arch: null,
  licences: [],
  tier: 'any',
  pluginsOnly: false,
  noGpu: false,
};

/** Lower-case words, so "Home  Assistant" and "home assistant" match the same. */
export function tokenize(q: string): string[] {
  return q
    .toLowerCase()
    .split(/[^a-z0-9#-]+/)
    .map((t) => t.replace(/^#/, ''))
    .filter(Boolean);
}

/**
 * Relevance of `app` for the query words: 0 means no match. Every word must match somewhere
 * (name, tagline, description, category label or sub-tags). Name hits weigh most.
 */
export function searchScore(app: CatalogApp, words: string[]): number {
  if (words.length === 0) return 1;
  const name = app.name.toLowerCase();
  const tags = (app.tags ?? []).map((t) => t.toLowerCase());
  const cat = `${app.category} ${CATEGORY_BY_SLUG[app.category]?.label ?? ''}`.toLowerCase();
  const text = `${app.tagline ?? ''} ${app.description}`.toLowerCase();
  let score = 0;
  for (const w of words) {
    if (name === w) score += 12;
    else if (name.startsWith(w)) score += 8;
    else if (name.includes(w)) score += 6;
    else if (tags.some((t) => t === w || t.startsWith(w))) score += 4;
    else if (cat.includes(w)) score += 3;
    else if (text.includes(w)) score += 1;
    else return 0;
  }
  return score;
}

const FIT_ORDER = { fits: 0, stale: 1, none: 2 } as const;

function passesFacets(app: CatalogApp, f: MarketFilters): boolean {
  if (app.deploy_class === 'core') return false;
  if (!f.classes.includes(app.deploy_class)) return false;
  if (f.category && app.category !== f.category) return false;
  if (f.tag && !(app.tags ?? []).includes(f.tag)) return false;
  if (f.arch && !app.archs.includes(f.arch)) return false;
  if (f.licences.length > 0 && (!app.licence_class || !f.licences.includes(app.licence_class))) return false;
  if (f.tier !== 'any' && app.tier !== f.tier) return false;
  if (f.pluginsOnly && !app.plugin) return false;
  if (f.noGpu && (app.requires?.gpu || app.placement?.gpu === 'required')) return false;
  return true;
}

/** Apps no node can run. List-only apps are never placed, so they never count as "does not fit". */
export function doesNotFit(app: CatalogApp): boolean {
  return app.deploy_class !== 'list-only' && app.fit?.verdict === 'none';
}

export interface FilterResult {
  apps: CatalogApp[];
  /** Hidden only because no node can run them (the "N hidden" line that turns the filter off). */
  hiddenByFit: number;
}

/** Filter and rank: best fit first, then relevance, then name. */
export function filterApps(apps: readonly CatalogApp[], f: MarketFilters): FilterResult {
  const words = tokenize(f.q);
  let hiddenByFit = 0;
  const scored: { app: CatalogApp; score: number }[] = [];
  for (const app of apps) {
    if (!passesFacets(app, f)) continue;
    const score = searchScore(app, words);
    if (score === 0) continue;
    if (f.fitsOnly && doesNotFit(app)) {
      hiddenByFit += 1;
      continue;
    }
    scored.push({ app, score });
  }
  scored.sort(
    (a, b) =>
      FIT_ORDER[a.app.fit?.verdict ?? 'fits'] - FIT_ORDER[b.app.fit?.verdict ?? 'fits'] ||
      b.score - a.score ||
      a.app.name.localeCompare(b.app.name),
  );
  return { apps: scored.map((s) => s.app), hiddenByFit };
}

/** Count per category with every filter applied except the category itself (chip counts). */
export function countByCategory(apps: readonly CatalogApp[], f: MarketFilters): Record<CategorySlug, number> {
  const base = { ...f, category: null, tag: null };
  const counts = Object.fromEntries(CATEGORIES.map((c) => [c.slug, 0])) as Record<CategorySlug, number>;
  for (const app of filterApps(apps, base).apps) counts[app.category] += 1;
  return counts;
}

/** Sub-tags in use inside a category, in the closed-list order, with counts. */
export function tagsInCategory(apps: readonly CatalogApp[], slug: CategorySlug, f: MarketFilters): { tag: string; count: number }[] {
  const inCat = filterApps(apps, { ...f, category: slug, tag: null }).apps;
  return (CATEGORY_BY_SLUG[slug]?.tags ?? [])
    .map((tag) => ({ tag, count: inCat.filter((a) => (a.tags ?? []).includes(tag)).length }))
    .filter((t) => t.count > 0);
}

/** How many filters differ from the defaults (the badge on the Filters button). */
export function activeFilterCount(f: MarketFilters): number {
  let n = 0;
  const same = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((x) => b.includes(x));
  if (!same(f.classes, DEFAULT_FILTERS.classes)) n++;
  if (f.fitsOnly !== DEFAULT_FILTERS.fitsOnly) n++;
  if (f.arch) n++;
  if (f.licences.length) n++;
  if (f.tier !== 'any') n++;
  if (f.pluginsOnly) n++;
  if (f.noGpu) n++;
  return n;
}

// ---------------------------------------------------------------- the one primary action

export type PrimaryAction =
  | { kind: 'open' }
  | { kind: 'request-install' }
  | { kind: 'request-deploy' }
  | { kind: 'upstream'; href: string | undefined }
  | { kind: 'none'; reason: string }
  | { kind: 'blocked'; reason: string };

/**
 * Exactly one primary action per app (TAXONOMY §4.5). Install is offered only when the hub would
 * accept it: scan fresh and passing (contract §10.3, §11.4) and some node fits (TAXONOMY §3.3).
 */
export function primaryAction(app: CatalogApp, now: number): PrimaryAction {
  if (app.deploy_class === 'core') return { kind: 'none', reason: 'Part of OneMind. It updates with the system.' };
  if (app.installed) return { kind: 'open' };
  if (app.deploy_class === 'list-only') return { kind: 'upstream', href: safeHttpUrl(app.links?.website ?? app.links?.github ?? app.source) };
  const block = installBlockReason(app.scan, app.tier, now);
  if (block) return { kind: 'blocked', reason: block };
  if (doesNotFit(app)) return { kind: 'blocked', reason: app.fit?.reason ? `No node can run it: ${app.fit.reason}` : 'No node can run it.' };
  return app.deploy_class === 'private' ? { kind: 'request-deploy' } : { kind: 'request-install' };
}

// ---------------------------------------------------------------- requests (P1, P4)

/** Contract §3 has install and remove; the rest are PROPOSED (PD-03, PD-06). */
export const CONTRACT_ACTIONS: readonly StoreActionType[] = ['app.install', 'app.remove'];

const VERB: Record<StoreActionType, string> = {
  'app.install': 'install',
  'app.remove': 'remove',
  'app.start': 'start',
  'app.stop': 'stop',
  'app.restart': 'restart',
  'app.update': 'update',
  'app.configure': 'configure',
  'app.delete_data': 'delete-data',
};

export function buildRequest(type: StoreActionType, app: Pick<CatalogApp, 'id' | 'name'>, extra: Record<string, unknown> = {}): StoreActionRequest {
  const params = { app_id: app.id, ...extra };
  const summary: Record<StoreActionType, string> = {
    'app.install': `Install ${app.name}${extra.node ? ` on ${String(extra.node)}` : ''}`,
    'app.remove': `Remove ${app.name}${extra.keep_data === false ? ' and delete its data' : ' (its data is kept)'}`,
    'app.start': `Start ${app.name}`,
    'app.stop': `Stop ${app.name}`,
    'app.restart': `Restart ${app.name}`,
    'app.update': `Update ${app.name}${extra.to_version ? ` to ${String(extra.to_version)}` : ''}`,
    'app.configure': `Change ${app.name} settings`,
    'app.delete_data': `Delete all data of ${app.name}`,
  };
  return { type, params, summary: summary[type] };
}

/** The REST call the UI makes (PRINCIPLES P4). Shown in a disclosure next to every request. */
export function apiEquivalent(req: StoreActionRequest): string {
  return `POST /v1/actions\n${JSON.stringify({ type: req.type, params: req.params }, null, 2)}`;
}

/** The CLI verb. All `onemind apps` verbs are planned, so the UI labels them as planned. */
export function cliEquivalent(req: StoreActionRequest): string {
  const extra = Object.entries(req.params)
    .filter(([k]) => k !== 'app_id')
    .map(([k, v]) => `--${k.replace(/_/g, '-')}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`);
  return ['onemind apps', VERB[req.type], req.params.app_id, ...extra].join(' ');
}

export function isProposedAction(type: StoreActionType): boolean {
  return !CONTRACT_ACTIONS.includes(type);
}

// ---------------------------------------------------------------- job progress (PU-06)

export const INSTALL_STEPS: readonly { state: JobState; label: string }[] = [
  { state: 'awaiting_approval', label: 'Awaiting approval' },
  { state: 'pulling', label: 'Pulling image' },
  { state: 'starting', label: 'Starting' },
  { state: 'healthy', label: 'Healthy' },
];

export const JOB_LABEL: Record<JobState, string> = {
  awaiting_approval: 'Awaiting approval',
  pulling: 'Pulling image',
  starting: 'Starting',
  healthy: 'Healthy',
  rolled_back: 'Rolled back',
  failed: 'Failed',
  denied: 'Denied',
  expired: 'Expired',
};

export const JOB_TONE = {
  awaiting_approval: 'warn',
  pulling: 'info',
  starting: 'info',
  healthy: 'ok',
  rolled_back: 'bad',
  failed: 'bad',
  denied: 'neutral',
  expired: 'neutral',
} as const satisfies Record<JobState, string>;

export function isJobActive(state: JobState): boolean {
  return state === 'awaiting_approval' || state === 'pulling' || state === 'starting';
}

/**
 * Where a job is on the four-step track. Terminal failures sit on the step they reached:
 * a rollback happens after start, a denial or expiry before pulling.
 */
export function jobStepIndex(state: JobState): number {
  switch (state) {
    case 'awaiting_approval':
    case 'denied':
    case 'expired':
      return 0;
    case 'pulling':
      return 1;
    case 'starting':
    case 'rolled_back':
    case 'failed':
      return 2;
    case 'healthy':
      return 3;
  }
}

/** Overall percent for a progress bar; undefined while indeterminate (no executor % yet). */
export function jobPercent(job: Pick<StoreJob, 'state' | 'percent'>): number | undefined {
  if (job.state === 'healthy') return 100;
  if (job.state === 'awaiting_approval') return 0;
  if (job.percent === undefined || !isJobActive(job.state)) return undefined;
  const p = Math.min(100, Math.max(0, job.percent));
  // pulling covers 0-70 %, starting 70-99 % of the bar.
  return Math.round(job.state === 'pulling' ? p * 0.7 : 70 + p * 0.29);
}

/** The demo's next state after "approve" ticks; the real source is the action record. */
export function nextJobState(state: JobState, healthy = true): JobState {
  if (state === 'awaiting_approval') return 'pulling';
  if (state === 'pulling') return 'starting';
  if (state === 'starting') return healthy ? 'healthy' : 'rolled_back';
  return state;
}

// ---------------------------------------------------------------- misc

export { tileHue, monogram } from '../components/AppIcon';

/** "1024" MB → "1 GB", "256" → "256 MB". */
export function formatMb(mb: number | undefined): string {
  if (mb === undefined || !Number.isFinite(mb)) return 'unknown';
  return mb >= 1024 ? `${Math.round((mb / 1024) * 10) / 10} GB` : `${mb} MB`;
}

/** True when the app's newest note is newer than its installed version. */
export function hasUpdate(installedVersion: string, update: { version: string } | undefined): boolean {
  return !!update && update.version !== installedVersion;
}
