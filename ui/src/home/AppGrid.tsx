// SPDX-License-Identifier: Apache-2.0
// Installed apps as a launcher grid, filterable by category (TAXONOMY.md §1) and by where
// the app came from (deployment class, §2). Each tile says its state in words, never only
// by the dot's colour; when the hub is not answering the state is "last known".
import { useMemo, useState } from 'react';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { cx } from '../lib/cx';
import { AppGlyph, CategoryIcon, StatusDot, appState } from './parts';
import { CATEGORIES, DEPLOY_CLASS, SOURCE_FILTERS, categoryOf, type CategorySlug, type SourceFilter } from './taxonomy';
import type { HomeApp } from './types';

export interface AppGridProps {
  apps: HomeApp[];
  hubLive: boolean;
  editing: boolean;
  pinned: string[];
  onTogglePin: (appId: string) => void;
  /** Open target: the app itself when it runs, else its page (true state, actions). */
  hrefFor: (app: HomeApp) => string;
  marketHref: string;
  pinsFull: boolean;
}

type CatFilter = 'all' | CategorySlug | 'none';

export function filterApps(apps: HomeApp[], cat: CatFilter, src: SourceFilter): HomeApp[] {
  const srcDef = SOURCE_FILTERS.find((s) => s.id === src);
  return apps.filter((a) => {
    const c = categoryOf(a.category)?.slug ?? 'none';
    if (cat !== 'all' && c !== cat) return false;
    if (srcDef && 'classes' in srcDef) return !!a.deploy_class && srcDef.classes.includes(a.deploy_class);
    return true;
  });
}

export function AppGrid({ apps, hubLive, editing, pinned, onTogglePin, hrefFor, marketHref, pinsFull }: AppGridProps) {
  const [cat, setCat] = useState<CatFilter>('all');
  const [src, setSrc] = useState<SourceFilter>('all');

  const cats = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of apps) {
      const k = categoryOf(a.category)?.slug ?? 'none';
      counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    const list: Array<{ id: CatFilter; name: string; count: number; icon?: string }> = CATEGORIES.filter((c) => counts.has(c.slug)).map((c) => ({ id: c.slug, name: c.name, count: counts.get(c.slug)!, icon: c.icon }));
    if (counts.has('none')) list.push({ id: 'none', name: 'Not categorised', count: counts.get('none')! });
    return list;
  }, [apps]);

  const sources = SOURCE_FILTERS.filter((s) => s.id === 'all' || apps.some((a) => a.deploy_class && 'classes' in s && s.classes.includes(a.deploy_class)));
  const shown = filterApps(apps, cat, src);

  return (
    <div className="omh-apps">
      <div className="omh-filters">
        <div className="omh-chips" role="group" aria-label="Category">
          <button type="button" className="omh-chip" aria-pressed={cat === 'all'} onClick={() => setCat('all')}>
            All <span className="omh-chip-count">{apps.length}</span>
          </button>
          {cats.map((c) => (
            <button key={c.id} type="button" className="omh-chip" aria-pressed={cat === c.id} onClick={() => setCat(c.id)}>
              {c.icon && <CategoryIcon category={{ icon: c.icon }} />}
              {c.name} <span className="omh-chip-count">{c.count}</span>
            </button>
          ))}
        </div>
        {sources.length > 2 && (
          <div className="omh-chips omh-chips-src" role="group" aria-label="Where apps come from">
            {sources.map((s) => (
              <button key={s.id} type="button" className="omh-chip omh-chip-quiet" aria-pressed={src === s.id} onClick={() => setSrc(s.id)}>
                {s.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {shown.length === 0 ? (
        <p className="omh-apps-empty">
          No installed apps match.{' '}
          <button
            type="button"
            className="omh-linkbtn"
            onClick={() => {
              setCat('all');
              setSrc('all');
            }}
          >
            Show all apps
          </button>
        </p>
      ) : (
        <ul className="omh-appgrid" aria-label="Installed apps">
          {shown.map((a) => {
            const st = appState(a, hubLive);
            const cls = a.deploy_class ? DEPLOY_CLASS[a.deploy_class] : undefined;
            const category = categoryOf(a.category);
            const isPinned = pinned.includes(a.id);
            return (
              <li key={a.id} className="omh-appcell">
                <a className="omh-app" href={hrefFor(a)} title={`${a.name}: ${a.description}`}>
                  <span className="omh-app-icon">
                    <AppGlyph app={a} size={60} />
                    <StatusDot tone={st.tone} pulse={st.pulse && hubLive} hollow={st.lastKnown} className="omh-app-dot" />
                  </span>
                  <span className="omh-app-name">{a.name}</span>
                  <span className="omh-app-state">
                    {st.label}
                    {a.update_available && (
                      <span className="omh-app-updtext">
                        <span aria-hidden="true"> · </span>
                        <span className="om-visually-hidden">, </span>update<span className="om-visually-hidden"> {a.update_available} available</span>
                      </span>
                    )}
                    {category && <span className="om-visually-hidden">, {category.name}</span>}
                    {a.plugin && <span className="om-visually-hidden">, adds a plugin</span>}
                  </span>
                  {/* One badge per tile: the deployment kind. "Plugin" stays in the accessible name and on the app page. */}
                  {cls?.badge && (
                    <span className="omh-app-badges">
                      <StatusPill tone={cls.tone} label={cls.badge} dot={false} />
                    </span>
                  )}
                </a>
                {editing && (
                  <button
                    type="button"
                    className={cx('omh-pin', isPinned && 'omh-pin-on')}
                    aria-pressed={isPinned}
                    disabled={!isPinned && pinsFull}
                    onClick={() => onTogglePin(a.id)}
                  >
                    <Icon name={isPinned ? 'check' : 'plus'} size={14} />
                    {isPinned ? 'In dock' : 'Dock'}
                    <span className="om-visually-hidden"> {a.name}</span>
                  </button>
                )}
              </li>
            );
          })}
          {cat === 'all' && src === 'all' && (
            <li className="omh-appcell">
              <a className="omh-app omh-app-add" href={marketHref}>
                <span className="omh-app-icon">
                  <span className="omh-glyph omh-glyph-add" style={{ width: 60, height: 60 }} aria-hidden="true">
                    <Icon name="plus" size={26} />
                  </span>
                </span>
                <span className="omh-app-name">Get apps</span>
                <span className="omh-app-state">Market</span>
              </a>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
