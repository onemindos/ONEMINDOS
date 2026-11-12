// SPDX-License-Identifier: Apache-2.0
// Home as a launcher (IA §2.1, parity PU-04): wallpaper, greeting with time and a weather
// slot, a search bar that opens the command palette, the widget grid ("Needs you" first),
// the installed apps by category, and a dock of pinned apps. Renders from data it is given;
// every action is a callback the host maps to the API (P4). Layout is controlled: the host
// stores it per person.
import { useEffect, useId, useMemo, useState } from 'react';
import './home.css';
import { Button } from '../components/Button';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { cx } from '../lib/cx';
import { freshness } from '../lib/freshness';
import { formatAgo, secondsSince } from '../lib/time';
import { AppGrid } from './AppGrid';
import { Dock } from './Dock';
import { clockText, dateText, greeting, summaryLine } from './greeting';
import type { HomeWallpaperId } from './homeTokens';
import { DEFAULT_LAYOUT, MAX_PINNED, dockApps, togglePin, type HomeLayout } from './layout';
import { nodeFreshness } from './parts';
import type { HomeApp, HomeData } from './types';
import { WidgetGallery } from './WidgetGallery';
import { WidgetGrid } from './WidgetGrid';
import { DEFAULT_LINKS, type CanDecide, type HomeLinks, type WidgetContext } from './widgets';
import type { ActionSummary } from '../components/ApprovalCard';

/** The hub's own answer ages too: stale after 30 s, offline after 120 s (contract §3). */
export const HUB_LIMITS = { staleAfter: 30, offlineAfter: 120 };
/** A weather reading older than this is labelled with its age. */
export const WEATHER_STALE_S = 3600;

/**
 * Home's own generated wallpaper, or `'host'` when the app already paints one behind every
 * screen (the appearance settings layer); Home then adds none of its own.
 */
export type HomeWallpaper = HomeWallpaperId | 'host';

export interface HomeScreenProps {
  data: HomeData;
  /** Hub clock, ms epoch. */
  now: number;
  /** Hub time zone (IANA), for the greeting and clock. */
  timeZone: string;
  personName?: string;
  layout: HomeLayout;
  onLayoutChange: (next: HomeLayout) => void;
  wallpaper?: HomeWallpaper;
  canDecide: CanDecide;
  onApprove?: (a: ActionSummary) => void;
  onDeny?: (a: ActionSummary) => void;
  busy?: ReadonlySet<string>;
  /** Opens the command palette (UX-P3). Also bound to Ctrl/Cmd+K while Home is shown. */
  onOpenSearch?: () => void;
  links?: Partial<HomeLinks>;
  /** Start in edit mode (screenshots, tests). */
  initialEditing?: boolean;
}

export function HomeScreen({
  data,
  now,
  timeZone,
  personName,
  layout,
  onLayoutChange,
  wallpaper = 'tide',
  canDecide,
  onApprove,
  onDeny,
  busy,
  onOpenSearch,
  links: linkOverrides,
  initialEditing = false,
}: HomeScreenProps) {
  const [editing, setEditing] = useState(initialEditing);
  const [galleryOpen, setGalleryOpen] = useState(false);
  const [announce, setAnnounce] = useState('');
  const widgetsHead = useId();
  const appsHead = useId();
  const links = useMemo(() => ({ ...DEFAULT_LINKS, ...linkOverrides }), [linkOverrides]);

  const hubAge = secondsSince(data.hub.observed_at, now);
  const hubState = freshness(hubAge, HUB_LIMITS);
  const hubLive = hubState === 'live';

  useEffect(() => {
    if (!onOpenSearch) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        onOpenSearch();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onOpenSearch]);

  const change = (next: HomeLayout, msg: string) => {
    if (next !== layout) onLayoutChange(next);
    setAnnounce(msg);
  };

  const apps = data.apps.state === 'ready' ? data.apps.data.filter((a) => a.installed) : [];
  const nodes = data.nodes.state === 'ready' ? data.nodes.data : [];
  const waiting = data.approvals.state === 'ready' ? data.approvals.data.filter((a) => a.state === 'awaiting_approval').length : 0;
  const nodeStates = nodes.map((n) => nodeFreshness(n, now));
  const summary = summaryLine({
    waiting,
    staleNodes: nodeStates.filter((s) => s === 'stale').length,
    offlineNodes: nodeStates.filter((s) => s === 'offline').length,
    unhealthyApps: apps.filter((a) => a.status === 'unhealthy').length,
    hubLive,
  });

  const hrefFor = (a: HomeApp) => (hubLive && a.status === 'running' && a.open_url ? a.open_url : links.app(a.id));
  const ctx: WidgetContext = { data, now, hubLive, hubAgo: formatAgo(hubAge), canDecide, onApprove, onDeny, busy, links, showSource: editing };
  const docked = dockApps(layout, apps);
  const w = data.weather;
  const weatherAge = w ? secondsSince(w.updated_at, now) : Number.NaN;

  return (
    <div className={cx('omh-home', `omh-wall-${wallpaper}`, editing && 'omh-editing')}>
      {wallpaper !== 'host' && <div className="omh-wall" aria-hidden="true" />}

      <header className="omh-hero">
        <div className="omh-hero-text">
          <p className="omh-date">
            <time dateTime={new Date(now).toISOString()}>
              {dateText(now, timeZone)} · {clockText(now, timeZone)}
            </time>
          </p>
          <h1 className="omh-greeting">{greeting(now, timeZone, personName)}</h1>
          <p className="omh-summary">{summary}</p>
        </div>
        {w && (
          <div className="omh-weather" aria-label="Weather">
            <span className="omh-weather-temp">{Math.round(w.temp_c)}°</span>
            <span className="omh-weather-text">
              <span>{w.summary}</span>
              <span className="omh-weather-src">
                {w.source} · {weatherAge > WEATHER_STALE_S ? <StatusPill tone="warn" label={`as of ${formatAgo(weatherAge)}`} /> : formatAgo(weatherAge)}
              </span>
            </span>
          </div>
        )}
      </header>

      <button type="button" className="omh-search" onClick={onOpenSearch} disabled={!onOpenSearch} aria-keyshortcuts="Control+K Meta+K">
        <Icon name="search" size={20} />
        <span className="omh-search-text">Search apps, nodes and settings, or request something</span>
        <kbd className="omh-kbd" aria-hidden="true">
          Ctrl K
        </kbd>
      </button>

      {!hubLive && (
        <div className={cx('omh-banner', hubState === 'stale' ? 'om-tone-warn' : 'om-tone-neutral')} role="status">
          <Icon name="alert" size={18} />
          <span>
            <strong>{hubState === 'stale' ? 'The hub is slow to answer.' : 'The hub is not answering.'}</strong> Showing the last known state from {formatAgo(hubAge)}. Nothing below is live, and
            decisions wait until it is back.
          </span>
        </div>
      )}

      <section className="omh-section" aria-labelledby={widgetsHead}>
        <div className="omh-section-head">
          <h2 id={widgetsHead}>Overview</h2>
          <div className="omh-section-actions">
            {editing && (
              <>
                <Button size="sm" icon="plus" onClick={() => setGalleryOpen(true)}>
                  Add widget
                </Button>
                <Button size="sm" variant="ghost" onClick={() => change({ ...DEFAULT_LAYOUT, pinned: layout.pinned }, 'Widgets reset to the default layout.')}>
                  Reset
                </Button>
              </>
            )}
            <Button size="sm" variant={editing ? 'primary' : 'secondary'} icon={editing ? 'check' : 'settings'} aria-pressed={editing} onClick={() => setEditing((e) => !e)}>
              {editing ? 'Done' : 'Edit Home'}
            </Button>
          </div>
        </div>
        {editing && <p className="omh-edit-hint">Drag a widget, or use its arrows. Pick S, M or L to resize. Changes are saved for you only.</p>}
        <WidgetGrid layout={layout} onChange={change} editing={editing} ctx={ctx} />
      </section>

      <section className="omh-section" aria-labelledby={appsHead}>
        <div className="omh-section-head">
          <h2 id={appsHead}>Your apps</h2>
          <a href={links.apps}>Market</a>
        </div>
        {data.apps.state === 'loading' && (
          <div className="omh-appgrid omh-appgrid-skel" role="status">
            <span className="om-visually-hidden">Loading apps</span>
            {Array.from({ length: 6 }, (_, i) => (
              <span key={i} className="omh-skel omh-skel-app" />
            ))}
          </div>
        )}
        {data.apps.state === 'error' && (
          <div className="omh-banner om-tone-bad" role="alert">
            <Icon name="alert" size={18} />
            <span>
              <strong>Apps could not be loaded.</strong> {data.apps.message} <code>{data.apps.error}</code>
            </span>
          </div>
        )}
        {data.apps.state === 'ready' &&
          (apps.length ? (
            <AppGrid apps={apps} hubLive={hubLive} editing={editing} pinned={layout.pinned} onTogglePin={(id) => change(togglePin(layout, id), layout.pinned.includes(id) ? 'Removed from the dock.' : 'Added to the dock.')} hrefFor={hrefFor} marketHref={links.apps} pinsFull={layout.pinned.length >= MAX_PINNED} />
          ) : (
            <div className="omh-apps-none">
              <p className="omh-empty-title">No apps yet</p>
              <p className="om-hint">Pick one from the Market. Installing is a request you approve.</p>
              <p className="om-hint">
                Or from a terminal: <code>onemind apps install &lt;id&gt;</code>
              </p>
              <a className="om-btn om-btn-primary" href={links.apps}>
                Browse the Market
              </a>
            </div>
          ))}
      </section>

      <Dock apps={docked} layout={layout} editing={editing} hubLive={hubLive} hrefFor={hrefFor} appsHref={links.apps} onChange={change} />

      <WidgetGallery open={galleryOpen} onClose={() => setGalleryOpen(false)} data={data} layout={layout} onAdd={change} />
      <p className="om-visually-hidden" role="status" aria-live="polite">
        {announce}
      </p>
    </div>
  );
}
