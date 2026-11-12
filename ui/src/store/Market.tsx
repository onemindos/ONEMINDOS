// SPDX-License-Identifier: Apache-2.0
// The Market (TAXONOMY §4, IA §2.2, PU-02): search, category rail with sub-tags, filters,
// Discover rails, and the results grid. Every install is a request that lands in Approvals (P1).
import { useId, useMemo, useState, type ReactNode } from 'react';
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { cx } from '../lib/cx';
import { AppTile, ClassPills, FitLine, LoadGate } from './bits';
import { CategoryIcon } from './CategoryIcon';
import { activeFilterCount, countByCategory, DEFAULT_FILTERS, filterApps, JOB_LABEL, primaryAction, tagsInCategory, type MarketFilters } from './logic';
import { BROWSABLE_CLASSES, CATEGORIES, CATEGORY_BY_SLUG, DEPLOY_CLASSES, LICENCE_CLASSES } from './taxonomy';
import type { Arch, CatalogApp, Collection, DeployClass, LicenceClass, LoadState, StoreJob } from './types';

export interface MarketHandlers {
  /** Opens the install review for `app` (the request is created after review). */
  onRequestInstall: (app: CatalogApp) => void;
  onOpen: (app: CatalogApp) => void;
  /** Asks to remove an installed app. Optional: only the screens that can send the request pass it. */
  onRequestRemove?: (app: CatalogApp) => void;
  /** Link to the app page. */
  appHref: (id: string) => string;
}

export interface MarketProps extends MarketHandlers {
  apps: CatalogApp[];
  state: LoadState;
  now: number;
  collections?: Collection[];
  featured?: { app_id: string; headline: string; blurb: string };
  /** Install requests in flight, for the "Needs you" rail. */
  jobs?: StoreJob[];
  initialFilters?: Partial<MarketFilters>;
  onRetry?: () => void;
  approvalsHref?: string;
}

/** Category rails on Discover (CRITIQUE #19); the rest sit behind a chip each. */
export const DISCOVER_RAILS = 4;

// ---------------------------------------------------------------- app card

export function AppCard({ app, now, onRequestInstall, onRequestRemove, onOpen, appHref, disabled }: MarketHandlers & { app: CatalogApp; now: number; disabled?: string }) {
  const action = primaryAction(app, now);
  const reasonId = useId();
  const cat = CATEGORY_BY_SLUG[app.category];
  const reason = disabled ?? (action.kind === 'blocked' || action.kind === 'none' ? action.reason : undefined);
  return (
    <article className={cx('om-store-card', action.kind === 'blocked' && 'om-store-card-muted')} aria-labelledby={`${reasonId}-name`}>
      <div className="om-store-card-top">
        <AppTile app={app} size={52} />
        <div className="om-store-card-titles">
          <h3 id={`${reasonId}-name`} className="om-store-card-name">
            <a href={appHref(app.id)} className="om-store-stretch">
              {app.name}
            </a>
          </h3>
          <p className="om-store-card-cat">
            {cat && <CategoryIcon name={cat.icon} size={14} />}
            {cat?.label ?? 'Uncategorised'}
            {app.tags && app.tags.length > 0 && <span className="om-store-card-tags"> · {app.tags.slice(0, 2).join(', ')}</span>}
          </p>
        </div>
      </div>
      <p className="om-store-card-desc">{app.tagline ?? app.description}</p>
      <ClassPills app={app} />
      {/* The trust facts the owner decides on, on the card itself (contract §10.3, §11.4). */}
      <p className="om-store-card-trust">
        Licence: {app.license}
        {app.scan && <> · Scan {app.scan.result === 'pass' ? 'passed' : 'failed'}</>}
        {app.installed && <> · <strong>Installed</strong></>}
      </p>
      <div className="om-store-card-foot">
        <FitLine fit={app.fit} listOnly={app.deploy_class === 'list-only'} />
        <div className="om-store-card-action">
          {action.kind === 'open' ? (
            <>
              <Button size="sm" icon="external" onClick={() => onOpen(app)} disabled={!!disabled} aria-describedby={disabled ? reasonId : undefined}>
                Open
              </Button>
              {onRequestRemove && (
                <Button size="sm" variant="ghost" disabled={!!disabled} onClick={() => onRequestRemove(app)}>
                  Remove<span className="om-visually-hidden"> {app.name}</span>
                </Button>
              )}
            </>
          ) :action.kind === 'upstream' ? (
            action.href ? (
              <a className="om-btn om-btn-secondary om-btn-sm" href={action.href} target="_blank" rel="noreferrer noopener">
                Get it upstream
                <Icon name="external" size={16} />
                <span className="om-visually-hidden"> (opens in a new tab)</span>
              </a>
            ) : null
          ) : action.kind === 'request-install' || action.kind === 'request-deploy' ? (
            <Button size="sm" variant="primary" disabled={!!disabled} aria-describedby={disabled ? reasonId : undefined} onClick={() => onRequestInstall(app)}>
              {action.kind === 'request-deploy' ? 'Request deploy' : 'Request install'}
              <span className="om-visually-hidden"> {app.name}</span>
            </Button>
          ) : (
            <Button size="sm" variant="primary" disabled aria-describedby={reasonId}>
              Request install<span className="om-visually-hidden"> {app.name}</span>
            </Button>
          )}
        </div>
      </div>
      {reason && (
        <p id={reasonId} className="om-store-card-why">
          {reason}
        </p>
      )}
    </article>
  );
}

// ---------------------------------------------------------------- rails

function Rail({ title, blurb, aside, children, icon }: { title: string; blurb?: string; aside?: ReactNode; children: ReactNode; icon?: ReactNode }) {
  const id = useId();
  return (
    <section className="om-store-rail" aria-labelledby={id}>
      <div className="om-store-rail-head">
        <div>
          <h2 id={id} className="om-store-rail-title">
            {icon}
            {title}
          </h2>
          {blurb && <p className="om-hint">{blurb}</p>}
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}

function RailRow({ apps, label, ...h }: MarketHandlers & { apps: CatalogApp[]; label: string; now: number; disabled?: string }) {
  return (
    <ul className="om-store-railrow" aria-label={label}>
      {apps.map((a) => (
        <li key={a.id}>
          <AppCard app={a} {...h} />
        </li>
      ))}
    </ul>
  );
}

function Featured({ app, headline, blurb, now, ...h }: MarketHandlers & { app: CatalogApp; headline: string; blurb: string; now: number; disabled?: string }) {
  const action = primaryAction(app, now);
  return (
    <section className="om-store-hero" aria-labelledby="om-store-hero-title">
      <div className="om-store-hero-art" aria-hidden="true">
        <span className="om-store-hero-orb" />
        <span className="om-store-hero-orb om-store-hero-orb-2" />
        <AppTile app={app} size={96} />
      </div>
      <div className="om-store-hero-text">
        <p className="om-store-eyebrow">
          <CategoryIcon name="sparkle" size={16} /> Featured · {CATEGORY_BY_SLUG[app.category]?.label}
        </p>
        <h2 id="om-store-hero-title" className="om-store-hero-title">
          {headline}
        </h2>
        <p className="om-store-hero-blurb">{blurb}</p>
        <div className="om-store-row">
          {action.kind === 'request-install' && (
            <Button variant="primary" disabled={!!h.disabled} onClick={() => h.onRequestInstall(app)}>
              Request install
            </Button>
          )}
          {action.kind === 'open' && (
            <Button icon="external" onClick={() => h.onOpen(app)}>
              Open {app.name}
            </Button>
          )}
          <a className="om-btn om-btn-secondary" href={h.appHref(app.id)}>
            About {app.name}
          </a>
          <ClassPills app={app} />
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- filters

function Check({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="om-store-check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{children}</span>
    </label>
  );
}

function FilterPanel({ f, set, id }: { f: MarketFilters; set: (p: Partial<MarketFilters>) => void; id: string }) {
  const toggle = <T,>(list: T[], v: T, on: boolean) => (on ? [...list, v] : list.filter((x) => x !== v));
  return (
    <div id={id} className="om-store-filters">
      <fieldset>
        <legend>Deployment class</legend>
        {BROWSABLE_CLASSES.map((c: DeployClass) => (
          <Check key={c} checked={f.classes.includes(c)} onChange={(on) => set({ classes: toggle(f.classes, c, on) })}>
            {DEPLOY_CLASSES[c].label}
            {c === 'market-community' && <span className="om-hint"> (not fully checked)</span>}
          </Check>
        ))}
        <Check checked={f.pluginsOnly} onChange={(v) => set({ pluginsOnly: v })}>
          Plugins only
        </Check>
      </fieldset>
      <fieldset>
        <legend>Fit</legend>
        <Check checked={f.fitsOnly} onChange={(v) => set({ fitsOnly: v })}>
          Runs on my nodes
        </Check>
        <Check checked={f.noGpu} onChange={(v) => set({ noGpu: v })}>
          Needs no GPU
        </Check>
        <label className="om-store-select">
          <span>Architecture</span>
          <select value={f.arch ?? ''} onChange={(e) => set({ arch: (e.target.value || null) as Arch | null })}>
            <option value="">Any</option>
            <option value="amd64">amd64 (Intel, AMD)</option>
            <option value="arm64">arm64 (Raspberry Pi, Apple, Jetson)</option>
          </select>
        </label>
      </fieldset>
      <fieldset>
        <legend>Licence class</legend>
        {(Object.keys(LICENCE_CLASSES) as LicenceClass[]).map((l) => (
          <Check key={l} checked={f.licences.includes(l)} onChange={(on) => set({ licences: toggle(f.licences, l, on) })}>
            {LICENCE_CLASSES[l].label} <span className="om-hint">({l})</span>
          </Check>
        ))}
      </fieldset>
      <fieldset>
        <legend>Market tier</legend>
        <label className="om-store-select">
          <span>Tier</span>
          <select value={f.tier} onChange={(e) => set({ tier: e.target.value as MarketFilters['tier'] })}>
            <option value="any">Any</option>
            <option value="verified">Verified</option>
            <option value="community">Community</option>
            <option value="blocked">Blocked (cannot install)</option>
          </select>
        </label>
      </fieldset>
    </div>
  );
}

// ---------------------------------------------------------------- page

export function Market({ apps, state, now, collections = [], featured, jobs = [], initialFilters, onRetry, approvalsHref = '#/approvals', ...h }: MarketProps) {
  const [f, setF] = useState<MarketFilters>({ ...DEFAULT_FILTERS, ...initialFilters });
  const [open, setOpen] = useState(false);
  const set = (p: Partial<MarketFilters>) => setF((cur) => ({ ...cur, ...p, ...(p.category !== undefined ? { tag: null } : {}) }));
  const filtersId = useId();
  const stale = state.kind === 'ready' && state.stale;
  const disabled = stale ? 'The hub is not answering. Requests wait until it is back.' : undefined;
  const hh = { ...h, now, disabled };

  const result = useMemo(() => filterApps(apps, f), [apps, f]);
  const counts = useMemo(() => countByCategory(apps, f), [apps, f]);
  const tags = useMemo(() => (f.category ? tagsInCategory(apps, f.category, f) : []), [apps, f]);
  const byId = useMemo(() => new Map(apps.map((a) => [a.id, a])), [apps]);
  const nFilters = activeFilterCount(f);
  const discover = !f.q && !f.category && !f.tag;
  const waiting = jobs.filter((j) => j.type === 'app.install' && j.state === 'awaiting_approval');
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  // CRITIQUE #19: Discover is the editorial rails plus the DISCOVER_RAILS fullest categories;
  // the other categories are chips that open their full list.
  const withApps = CATEGORIES.filter((c) => result.apps.some((a) => a.category === c.slug));
  const fullest = new Set([...withApps].sort((a, b) => (counts[b.slug] ?? 0) - (counts[a.slug] ?? 0)).slice(0, DISCOVER_RAILS));
  const railCats = withApps.filter((c) => fullest.has(c));
  const moreCats = withApps.filter((c) => !railCats.includes(c));

  const visible = (ids: string[]) => {
    const shown = new Set(result.apps.map((a) => a.id));
    return ids.map((id) => byId.get(id)).filter((a): a is CatalogApp => !!a && shown.has(a.id));
  };

  return (
    <div className="om-store">
      <div className="om-store-toolbar">
        <label className="om-store-search">
          <Icon name="search" size={18} />
          <span className="om-visually-hidden">Search apps by name, purpose or tag</span>
          <input type="search" placeholder="Search apps, e.g. photos, zigbee, #rss" value={f.q} onChange={(e) => set({ q: e.target.value })} />
        </label>
        <button type="button" className="om-btn om-btn-secondary" aria-expanded={open} aria-controls={filtersId} onClick={() => setOpen((o) => !o)}>
          <CategoryIcon name="filter" size={18} />
          Filters
          {nFilters > 0 && (
            <span className="om-store-count" aria-label={`${nFilters} changed`}>
              {nFilters}
            </span>
          )}
        </button>
      </div>
      {open && <FilterPanel f={f} set={set} id={filtersId} />}

      <div className="om-store-cats" role="group" aria-label="Category">
        <button type="button" className="om-store-chip" aria-pressed={!f.category} onClick={() => set({ category: null })}>
          <CategoryIcon name="grid" size={16} />
          All <span className="om-store-chip-n">{total}</span>
        </button>
        {CATEGORIES.map((c) => (
          <button
            key={c.slug}
            type="button"
            className="om-store-chip"
            aria-pressed={f.category === c.slug}
            onClick={() => set({ category: f.category === c.slug ? null : c.slug })}
          >
            <CategoryIcon name={c.icon} size={16} />
            {c.label} <span className="om-store-chip-n">{counts[c.slug]}</span>
          </button>
        ))}
      </div>
      {f.category && tags.length > 0 && (
        <div className="om-store-tagrow" role="group" aria-label={`${CATEGORY_BY_SLUG[f.category].label} sub-tags`}>
          {tags.map((t) => (
            <button key={t.tag} type="button" className="om-store-chip om-store-chip-sm" aria-pressed={f.tag === t.tag} onClick={() => set({ tag: f.tag === t.tag ? null : t.tag })}>
              #{t.tag} <span className="om-store-chip-n">{t.count}</span>
            </button>
          ))}
        </div>
      )}

      <LoadGate state={state} now={now} what="app catalog" onRetry={onRetry}>
        {discover ? (
          <div className="om-store-discover">
            {featured && byId.get(featured.app_id) && <Featured app={byId.get(featured.app_id)!} headline={featured.headline} blurb={featured.blurb} {...hh} />}
            {waiting.length > 0 && (
              <Rail title="Needs you" blurb="Install requests waiting for an owner's approval." icon={<Icon name="approvals" />} aside={<a href={approvalsHref}>Open Approvals</a>}>
                <ul className="om-store-needs">
                  {waiting.map((j) => (
                    <li key={j.action_id}>
                      <AppTile app={{ id: j.app_id, name: j.app_name }} size={36} />
                      <span>
                        <strong>{j.app_name}</strong>
                        <span className="om-hint"> · asked by {j.requested_by ?? 'you'}</span>
                      </span>
                      <StatusPill tone="warn" label={JOB_LABEL[j.state]} />
                    </li>
                  ))}
                </ul>
              </Rail>
            )}
            {collections.map((c) => {
              const list = visible(c.app_ids);
              return list.length ? (
                <Rail key={c.id} title={c.title} blurb={c.blurb}>
                  <RailRow apps={list} label={c.title} {...hh} />
                </Rail>
              ) : null;
            })}
            {railCats.map((c) => {
              const list = result.apps.filter((a) => a.category === c.slug).slice(0, 8);
              return list.length ? (
                <Rail
                  key={c.slug}
                  title={c.label}
                  icon={<CategoryIcon name={c.icon} />}
                  aside={
                    <button type="button" className="om-btn om-btn-ghost om-btn-sm" onClick={() => set({ category: c.slug })}>
                      See all {counts[c.slug]}
                      <span className="om-visually-hidden"> {c.label} apps</span>
                    </button>
                  }
                >
                  <RailRow apps={list} label={c.label} {...hh} />
                </Rail>
              ) : null;
            })}
            {moreCats.length > 0 && (
              <Rail title="More categories" blurb="Discover shows the four fullest categories. Every app is one tap away.">
                <div className="om-store-cats om-store-cats-wrap" role="group" aria-label="More categories">
                  {moreCats.map((c) => (
                    <button key={c.slug} type="button" className="om-store-chip" aria-pressed={false} onClick={() => set({ category: c.slug })}>
                      <CategoryIcon name={c.icon} size={16} />
                      {c.label} <span className="om-store-chip-n">{counts[c.slug]}</span>
                    </button>
                  ))}
                </div>
              </Rail>
            )}
            {result.apps.length === 0 && <NoResults f={f} hidden={result.hiddenByFit} reset={() => setF({ ...DEFAULT_FILTERS })} />}
          </div>
        ) : (
          <section aria-labelledby="om-store-results" className="om-store-results">
            <div className="om-store-rail-head">
              <h2 id="om-store-results" className="om-store-rail-title">
                {f.category ? CATEGORY_BY_SLUG[f.category].label : 'Results'}
                {f.tag ? ` · #${f.tag}` : ''}
              </h2>
              <p className="om-hint" role="status" aria-live="polite">
                {result.apps.length} {result.apps.length === 1 ? 'app' : 'apps'}
                {f.q ? ` for "${f.q}"` : ''}
              </p>
            </div>
            {result.apps.length > 0 ? (
              <ul className="om-store-grid" aria-label="Apps">
                {result.apps.map((a) => (
                  <li key={a.id}>
                    <AppCard app={a} {...hh} />
                  </li>
                ))}
              </ul>
            ) : (
              <NoResults f={f} hidden={result.hiddenByFit} reset={() => setF({ ...DEFAULT_FILTERS })} />
            )}
          </section>
        )}
        {result.hiddenByFit > 0 && (
          <p className="om-store-hidden-line">
            {result.hiddenByFit} {result.hiddenByFit === 1 ? 'app is' : 'apps are'} hidden because no node can run {result.hiddenByFit === 1 ? 'it' : 'them'}.{' '}
            <button type="button" className="om-store-linkbtn" onClick={() => set({ fitsOnly: false })}>
              Show them anyway
            </button>
          </p>
        )}
      </LoadGate>
    </div>
  );
}

function NoResults({ f, hidden, reset }: { f: MarketFilters; hidden: number; reset: () => void }) {
  const q = [f.category && `--category ${f.category}`, f.tag && `--tag ${f.tag}`, f.q && `--search "${f.q}"`].filter(Boolean).join(' ');
  return (
    <EmptyState icon="search" title="No apps match" command={`onemind apps list ${q}`.trim()} action={<Button onClick={reset}>Clear search and filters</Button>}>
      <p>
        Nothing in the Market matches these filters{hidden ? `, and ${hidden} more need a node you do not have` : ''}. Community apps are hidden by default: turn them on
        under Filters.
      </p>
    </EmptyState>
  );
}

