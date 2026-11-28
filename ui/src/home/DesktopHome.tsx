// SPDX-License-Identifier: Apache-2.0
// Atlas Home on the desktop (final design screens 01, 01b, 08b): the desktop itself, not a page.
// A column of tiles sits on the wallpaper at the left: the greeting and one summary sentence, the
// box status, then the person's tiles ("Needs you" first). Windows open over the rest of the
// wallpaper. Edit mode edits Home and the dock together: tiles move, resize and go back to the
// tray, and apps go in or out of the dock. Renders from data it is given; every action is a
// callback the host maps to the API (P4). No search bar and no app grid: the strip, the dock and
// the launcher carry those on the desktop.
import { useId, useMemo, useState, type ReactNode } from 'react';
import './home.css';
import './desktopHome.css';
import { Button } from '../components/Button';
import { Icon } from '../components/Icon';
import { cx } from '../lib/cx';
import { freshness } from '../lib/freshness';
import { formatAgo, secondsSince } from '../lib/time';
import type { ActionSummary } from '../components/ApprovalCard';
import { greetingParts } from './greeting';
import { HUB_LIMITS } from './HomeScreen';
import { addWidget, hasWidget, MAX_PINNED, MAX_WIDGETS, togglePin, type HomeLayout } from './layout';
import { AppGlyph, nodeFreshness } from './parts';
import type { HomeData } from './types';
import { galleryOptions } from './WidgetGallery';
import { WidgetGrid } from './WidgetGrid';
import { DEFAULT_LINKS, type CanDecide, type HomeLinks, type WidgetContext } from './widgets';

export interface DesktopHomeProps {
  data: HomeData;
  /** Hub clock, ms epoch. */
  now: number;
  timeZone: string;
  personName?: string;
  layout: HomeLayout;
  onLayoutChange: (next: HomeLayout) => void;
  /** What "Reset to default" goes back to (the dock pins are kept). */
  defaultLayout: HomeLayout;
  canDecide: CanDecide;
  onApprove?: (a: ActionSummary) => void;
  onDeny?: (a: ActionSummary) => void;
  busy?: ReadonlySet<string>;
  links?: Partial<HomeLinks>;
  onRetry?: () => void;
  /** A host's optional command bar, under the greeting. */
  commandBar?: ReactNode;
  /** Box status from the host, shown right under the greeting (status first). */
  status?: ReactNode;
  /** Host content at the end of the column (recent visits). */
  footer?: ReactNode;
  /** Start in edit mode (screenshots, tests). */
  initialEditing?: boolean;
}

export interface DesktopSummary {
  lead: string;
  rest: string;
}

/** Two sentences: what needs the person (bold), then what is not fine, else that everything else runs. */
export function desktopSummary(s: { waiting: number; staleNodes: number; offlineNodes: number; unhealthyApps: number; connecting: boolean; answering: boolean }): DesktopSummary {
  if (s.connecting) return { lead: 'Connecting to the hub.', rest: '' };
  if (!s.answering) return { lead: 'The hub is not answering.', rest: 'Everything here is its last known state.' };
  const lead = s.waiting ? `${s.waiting} ${s.waiting === 1 ? 'request needs' : 'requests need'} you.` : 'Nothing needs you.';
  const bits: string[] = [];
  if (s.unhealthyApps) bits.push(`${s.unhealthyApps} ${s.unhealthyApps === 1 ? 'app is' : 'apps are'} unhealthy`);
  if (s.staleNodes) bits.push(`${s.staleNodes} ${s.staleNodes === 1 ? 'machine is' : 'machines are'} late with a heartbeat`);
  if (s.offlineNodes) bits.push(`${s.offlineNodes} ${s.offlineNodes === 1 ? 'machine is' : 'machines are'} offline`);
  if (!bits.length) return { lead, rest: s.waiting ? 'Everything else is running.' : 'Everything is running.' };
  const text = bits.join(' and ');
  return { lead, rest: `${text.charAt(0).toUpperCase()}${text.slice(1)}.` };
}

export function DesktopHome({ data, now, timeZone, personName, layout, onLayoutChange, defaultLayout, canDecide, onApprove, onDeny, busy, links: linkOverrides, onRetry, commandBar, status, footer, initialEditing = false }: DesktopHomeProps) {
  const [editing, setEditing] = useState(initialEditing);
  const [announce, setAnnounce] = useState('');
  const tilesHead = useId();
  const links = useMemo(() => ({ ...DEFAULT_LINKS, ...linkOverrides }), [linkOverrides]);

  const hubAge = secondsSince(data.hub.observed_at, now);
  const hubLive = freshness(hubAge, HUB_LIMITS) === 'live';
  const neverSeen = !Number.isFinite(hubAge) || !(Date.parse(data.hub.observed_at) > 0);
  const connecting = [data.nodes, data.apps, data.approvals].every((s) => s.state === 'loading');
  const apps = data.apps.state === 'ready' ? data.apps.data.filter((a) => a.installed) : [];
  const nodeStates = (data.nodes.state === 'ready' ? data.nodes.data : []).map((n) => nodeFreshness(n, now));
  const summary = desktopSummary({
    waiting: data.approvals.state === 'ready' ? data.approvals.data.filter((a) => a.state === 'awaiting_approval').length : 0,
    staleNodes: nodeStates.filter((s) => s === 'stale').length,
    offlineNodes: nodeStates.filter((s) => s === 'offline').length,
    unhealthyApps: apps.filter((a) => a.status === 'unhealthy').length,
    connecting,
    answering: hubLive && !neverSeen,
  });
  const { hello, who } = greetingParts(now, timeZone, personName);

  const change = (next: HomeLayout, msg: string) => {
    if (next !== layout) onLayoutChange(next);
    setAnnounce(msg);
  };
  const ctx: WidgetContext = { data, now, hubLive, hubAgo: formatAgo(hubAge), canDecide, onApprove, onDeny, busy, links, showSource: editing, onRetry };
  const { builtin, apps: appTiles } = galleryOptions(data);
  const tray = [...builtin, ...appTiles].filter((o) => !hasWidget(layout, o.widget));
  const full = layout.widgets.length >= MAX_WIDGETS;

  return (
    <div className={cx('omd-home', editing && 'omd-editing')}>
      {editing && (
        <div className="omd-editbar" role="region" aria-label="Editing Home">
          <Icon name="settings" size={18} />
          <p>
            <strong>Editing Home and dock.</strong> Drag a tile or use its arrows to move it, × to remove, + to add. Nothing is lost: removed tiles go back to the tray.
          </p>
          <Button size="sm" variant="secondary" onClick={() => change({ ...defaultLayout, pinned: layout.pinned }, 'Home is back to the default tiles.')}>
            Reset to default
          </Button>
          <Button size="sm" variant="primary" onClick={() => { setEditing(false); setAnnounce('Done editing Home.'); }}>
            Done
          </Button>
        </div>
      )}

      <div className="omd-column">
        <header className="omd-hero">
          <h1 className="omd-greeting">{who ? `${hello}, ${who}` : hello}</h1>
          <p className="omd-summary">
            <strong>{summary.lead}</strong>
            {summary.rest && ` ${summary.rest}`}
          </p>
          {!hubLive && !connecting && (
            <p className="omd-hubage" role="status">
              <Icon name="alert" size={16} />
              {neverSeen ? 'Nothing has loaded yet, so nothing here is live.' : `Last answer from the hub ${formatAgo(hubAge)}. Decisions wait until it is back.`}
            </p>
          )}
          {!editing && (
            <button type="button" className="omd-edit" onClick={() => setEditing(true)}>
              <Icon name="settings" size={16} /> Edit Home and dock
            </button>
          )}
        </header>

        {commandBar}
        {status}

        <section className="omd-tiles" aria-labelledby={tilesHead}>
          <h2 id={tilesHead} className="om-visually-hidden">Home tiles</h2>
          <WidgetGrid layout={layout} onChange={change} editing={editing} ctx={ctx} />
        </section>

        {footer}
      </div>

      {editing && (
        <aside className="omd-tray" aria-label="Add to Home">
          <h2>Add to Home</h2>
          <p className="om-hint">{full ? `Home holds up to ${MAX_WIDGETS} tiles. Remove one to add another.` : 'Tiles from OneMind and from your apps. An app tile always says which app made it.'}</p>
          {tray.length ? (
            <ul className="omd-tray-list">
              {tray.map((o) => (
                <li key={o.key}>
                  <span className="omd-tray-glyph">{o.glyph}</span>
                  <span className="omd-tray-text">
                    <span className="omd-tray-title">{o.title}</span>
                    <span className="om-hint">{o.blurb}</span>
                  </span>
                  <button type="button" className="omd-tray-add" disabled={full} aria-label={`Add ${o.title} to Home`} onClick={() => change(addWidget(layout, o.widget), `${o.title} added at the end of Home.`)}>
                    <Icon name="plus" size={16} />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="om-hint">Every tile is on Home.</p>
          )}
          <h2>In the dock</h2>
          {apps.length ? (
            <ul className="omd-tray-list">
              {apps.map((a) => {
                const on = layout.pinned.includes(a.id);
                return (
                  <li key={a.id}>
                    <AppGlyph app={a} size={28} />
                    <span className="omd-tray-text">
                      <span className="omd-tray-title">{a.name}</span>
                    </span>
                    <button type="button" className="omd-tray-add" aria-pressed={on} disabled={!on && layout.pinned.length >= MAX_PINNED} aria-label={`${a.name} in the dock`}
                      onClick={() => change(togglePin(layout, a.id), on ? `${a.name} left the dock.` : `${a.name} is in the dock.`)}>
                      <Icon name={on ? 'check' : 'plus'} size={16} />
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="om-hint">No apps installed yet. Apps you install from the Market can go in the dock.</p>
          )}
          <p className="om-hint omd-tray-foot">Size: pick S, M or L on a tile. Your Home is saved for you only.</p>
        </aside>
      )}

      <p className="om-visually-hidden" role="status" aria-live="polite">
        {announce}
      </p>
    </div>
  );
}
