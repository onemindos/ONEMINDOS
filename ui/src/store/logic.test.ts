// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { catalog, NOW } from '../../demo/src/store/fixtures';
import { filterLogs } from './LogViewer';
import { appStateView } from './Installed';
import { reviewSteps } from './InstallReview';
import {
  activeFilterCount,
  apiEquivalent,
  buildRequest,
  cliEquivalent,
  countByCategory,
  DEFAULT_FILTERS,
  filterApps,
  isProposedAction,
  jobPercent,
  jobStepIndex,
  monogram,
  nextJobState,
  primaryAction,
  searchScore,
  tagsInCategory,
  tileHue,
  tokenize,
} from './logic';
import { TILE_HUES, TILE_TEXT } from './storeTokens';
import { CATEGORIES, isKnownTag } from './taxonomy';

const ids = (r: { apps: { id: string }[] }) => r.apps.map((a) => a.id);

describe('taxonomy', () => {
  it('has the 16 categories of TAXONOMY §1 in order, with unique slugs', () => {
    expect(CATEGORIES.map((c) => c.slug)).toEqual([
      'home', 'files', 'media', 'notes', 'productivity', 'communication', 'ai', 'automation',
      'network', 'monitoring', 'news', 'developer', 'family', 'finance', 'learning', 'field',
    ]);
  });
  it('fixtures only use sub-tags from each category closed list (max 3)', () => {
    for (const a of catalog) {
      expect(a.tags?.length ?? 0).toBeLessThanOrEqual(3);
      for (const t of a.tags ?? []) expect(isKnownTag(a.category, t), `${a.id} #${t}`).toBe(true);
    }
  });
});

describe('search and filters', () => {
  it('tokenizes and strips # from tags', () => {
    expect(tokenize('  #RSS  Photos ')).toEqual(['rss', 'photos']);
  });
  it('ranks name hits above tag and description hits; every word must match', () => {
    const imm = catalog.find((a) => a.id === 'immich')!;
    expect(searchScore(imm, ['immich'])).toBeGreaterThan(searchScore(imm, ['photos']));
    expect(searchScore(imm, ['photos', 'nonsense'])).toBe(0);
  });
  it('searches across categories and sub-tags', () => {
    expect(ids(filterApps(catalog, { ...DEFAULT_FILTERS, q: 'zigbee' }))).toContain('home-assistant');
    expect(ids(filterApps(catalog, { ...DEFAULT_FILTERS, q: 'field' }))).toContain('opentakserver');
  });
  it('never shows core apps, and hides community apps by default', () => {
    const r = ids(filterApps(catalog, DEFAULT_FILTERS));
    expect(r).not.toContain('restic');
    expect(r).not.toContain('searxng');
    expect(ids(filterApps(catalog, { ...DEFAULT_FILTERS, classes: [...DEFAULT_FILTERS.classes, 'market-community'] }))).toContain('searxng');
  });
  it('"Runs on my nodes" hides apps that fit nowhere and counts them', () => {
    const on = filterApps(catalog, DEFAULT_FILTERS);
    expect(ids(on)).not.toContain('ollama');
    expect(on.hiddenByFit).toBe(1);
    const off = filterApps(catalog, { ...DEFAULT_FILTERS, fitsOnly: false });
    expect(ids(off)).toContain('ollama');
    expect(off.hiddenByFit).toBe(0);
  });
  it('sorts fitting apps before stale and non-fitting ones', () => {
    const r = filterApps(catalog, { ...DEFAULT_FILTERS, fitsOnly: false });
    const pos = (id: string) => ids(r).indexOf(id);
    expect(pos('freshrss')).toBeGreaterThan(pos('immich'));
    expect(pos('ollama')).toBeGreaterThan(pos('freshrss'));
  });
  it('filters by category, tag, arch, licence class, tier, plugin and GPU', () => {
    expect(ids(filterApps(catalog, { ...DEFAULT_FILTERS, category: 'files', tag: 'photos' }))).toEqual(['immich']);
    expect(filterApps(catalog, { ...DEFAULT_FILTERS, licences: ['L3'] }).apps.every((a) => a.licence_class === 'L3')).toBe(true);
    expect(ids(filterApps(catalog, { ...DEFAULT_FILTERS, tier: 'blocked' }))).toEqual(['traccar']);
    expect(filterApps(catalog, { ...DEFAULT_FILTERS, pluginsOnly: true }).apps.every((a) => a.plugin)).toBe(true);
    expect(ids(filterApps(catalog, { ...DEFAULT_FILTERS, fitsOnly: false, noGpu: true }))).not.toContain('ollama');
    expect(filterApps(catalog, { ...DEFAULT_FILTERS, arch: 'arm64' }).apps.every((a) => a.archs.includes('arm64'))).toBe(true);
  });
  it('counts per category ignoring the selected category, and lists used sub-tags', () => {
    const c = countByCategory(catalog, { ...DEFAULT_FILTERS, category: 'media' });
    expect(c.files).toBe(3);
    expect(c.field).toBe(2);
    expect(tagsInCategory(catalog, 'files', DEFAULT_FILTERS).map((t) => t.tag)).toEqual(['cloud', 'photos', 'sync', 'documents', 'backup', 'calendar-contacts']);
  });
  it('counts changed filters', () => {
    expect(activeFilterCount(DEFAULT_FILTERS)).toBe(0);
    expect(activeFilterCount({ ...DEFAULT_FILTERS, arch: 'arm64', fitsOnly: false })).toBe(2);
  });
});

describe('primary action', () => {
  const get = (id: string) => primaryAction(catalog.find((a) => a.id === id)!, NOW);
  it('offers exactly one action per class and state', () => {
    expect(get('home-assistant').kind).toBe('open');
    expect(get('immich').kind).toBe('request-install');
    expect(get('my-garage-dashboard').kind).toBe('request-deploy');
    expect(get('invoice-ninja')).toEqual({ kind: 'upstream', href: 'https://invoiceninja.com/' });
    expect(get('restic').kind).toBe('none');
  });
  it('blocks with the reason: stale scan, blocked tier, no node fits', () => {
    expect(get('grafana')).toMatchObject({ kind: 'blocked', reason: expect.stringContaining('more than 7 days') });
    expect(get('traccar')).toMatchObject({ kind: 'blocked', reason: expect.stringContaining('Blocked') });
    expect(get('ollama')).toMatchObject({ kind: 'blocked', reason: expect.stringContaining('GPU') });
  });
});

describe('requests', () => {
  it('builds the request, the API equivalent and the planned CLI line', () => {
    const r = buildRequest('app.remove', { id: 'ntfy', name: 'ntfy' }, { keep_data: true });
    expect(r.summary).toBe('Remove ntfy (its data is kept)');
    expect(apiEquivalent(r)).toContain('"type": "app.remove"');
    expect(cliEquivalent(r)).toBe('onemind apps remove ntfy --keep-data=true');
  });
  it('marks only install and remove as contract actions', () => {
    expect(isProposedAction('app.install')).toBe(false);
    expect(isProposedAction('app.remove')).toBe(false);
    expect(isProposedAction('app.restart')).toBe(true);
    expect(isProposedAction('app.delete_data')).toBe(true);
  });
});

describe('jobs', () => {
  it('walks awaiting approval → pulling → starting → healthy | rolled back', () => {
    expect(nextJobState('awaiting_approval')).toBe('pulling');
    expect(nextJobState('pulling')).toBe('starting');
    expect(nextJobState('starting')).toBe('healthy');
    expect(nextJobState('starting', false)).toBe('rolled_back');
    expect(nextJobState('healthy')).toBe('healthy');
  });
  it('places terminal states on the step they reached', () => {
    expect(jobStepIndex('denied')).toBe(0);
    expect(jobStepIndex('rolled_back')).toBe(2);
    expect(jobStepIndex('healthy')).toBe(3);
  });
  it('maps executor percent onto one bar, indeterminate without a percent', () => {
    expect(jobPercent({ state: 'pulling', percent: 100 })).toBe(70);
    expect(jobPercent({ state: 'starting', percent: 100 })).toBe(99);
    expect(jobPercent({ state: 'starting' })).toBeUndefined();
    expect(jobPercent({ state: 'healthy' })).toBe(100);
  });
});

describe('install review steps', () => {
  it('generates only the steps that apply, in order', () => {
    const ha = catalog.find((a) => a.id === 'home-assistant')!;
    expect(reviewSteps(ha)).toEqual(['node', 'devices', 'network', 'storage', 'exposure', 'review']);
    const sx = catalog.find((a) => a.id === 'searxng')!;
    expect(reviewSteps(sx)).toEqual(['community', 'node', 'review']);
  });
});

describe('honest state (P2)', () => {
  it('says stale or unknown instead of a cached running', () => {
    const at = (s: number) => new Date(NOW - s * 1000).toISOString();
    expect(appStateView({ state: 'running', checked_at: at(5) }, NOW)).toMatchObject({ label: 'Running', live: true });
    expect(appStateView({ state: 'running', checked_at: at(75) }, NOW)).toMatchObject({ label: 'Stale', detail: 'last known running 1 min ago', live: false });
    expect(appStateView({ state: 'running', checked_at: at(600) }, NOW)).toMatchObject({ label: 'Unknown', live: false });
    expect(appStateView({ state: 'running', checked_at: 'garbage' }, NOW)).toMatchObject({ label: 'Unknown', detail: 'never checked' });
  });
  it('filters logs by level and text', () => {
    const lines = [
      { at: '', level: 'info' as const, text: 'a' },
      { at: '', level: 'warn' as const, text: 'b zigbee' },
      { at: '', level: 'error' as const, text: 'c' },
    ];
    expect(filterLogs(lines, 'warn', '').map((l) => l.text)).toEqual(['b zigbee', 'c']);
    expect(filterLogs(lines, 'all', 'ZIG').map((l) => l.text)).toEqual(['b zigbee']);
  });
});

describe('tiles and store tokens', () => {
  it('gives each id a stable hue and a monogram', () => {
    expect(tileHue('immich')).toBe(tileHue('immich'));
    expect(tileHue('x')).toBeGreaterThanOrEqual(0);
    expect(monogram('Home Assistant')).toBe('HA');
    expect(monogram('ntfy')).toBe('N');
  });
  const lum = (hex: string) => {
    const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0]! + 0.7152 * c[1]! + 0.0722 * c[2]!;
  };
  const contrast = (a: string, b: string) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p) as [number, number];
    return (x + 0.05) / (y + 0.05);
  };
  it.each(TILE_HUES.map((h) => [h.name, h] as const))('%s tile: white monogram ≥ 4.5:1 on both gradient stops', (_n, h) => {
    expect(contrast(TILE_TEXT, h.a)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(TILE_TEXT, h.b)).toBeGreaterThanOrEqual(4.5);
  });
});
