// SPDX-License-Identifier: Apache-2.0
// Map v0 (#653; dock slot 2 of the Atlas design, "The map"): the box, its nodes, the machines on them and every
// asset with a live value, on one plan of the owner's own place. Sites and floors on the left with layer switches
// and state filters; the plan (a metre grid, north up) or a list in the middle; the asset card on the right.
// Every value label prints its age. Read only: the Map never moves anything (D-027); a change is a request that
// waits in Approvals, made from the screen that owns the thing (Machines, Nodes).
// Base layer: none in v0. The plan is drawn from the site record itself, so no map library is loaded; an
// offline base map (MapLibre over the installed packs, #1020/#1066) is a follow-up.
import { useMemo, useState, type CSSProperties } from 'react';
import { Link } from 'react-router';
import { type components } from '@onemind/sdk';
import { EmptyState, FRESHNESS_GLYPH, PageHeader, StatusGlyph, type Freshness } from '@onemind/ui';
import type { MachineRecord } from '../../api/types';
import { useHub } from '../../data/hub';
import { useGateway, viaSdk } from '../../lib/gateway';
import { usePoll } from '../../lib/hooks';
import { useSignedIn } from '../../session';
import { counts, gridStep, labelOf, layerName, mapItems, planBounds, shortAge, type GeoSite, type MapItem } from './model';
import { useAssetStream, type AssetsState, type FeedState } from './useAssetStream';
import { useShell } from '../../shell/Shell';
import './map.css';

type Packs = components['schemas']['Packs'];
type View = 'plan' | 'list';

const STATE_WORD: Record<Freshness, string> = { live: 'Fresh', stale: 'Stale', offline: 'Offline', unknown: 'Unknown' };
const FEED_WORD: Record<FeedState, string> = {
  off: 'No live feed in demo mode',
  connecting: 'Connecting to the live feed…',
  live: 'Live',
  reconnecting: 'Reconnecting… showing the last values received',
  denied: 'This account may not read asset values',
  unavailable: 'Live feed unavailable; showing nodes and machines only',
};
/** What the hub said about its own asset values in stream.snapshot (core fanout.py AssetState). */
const ASSETS_WORD: Record<Exclude<AssetsState, 'ready'>, string> = {
  pending: 'Asset values pending: the hub is still waiting for its message bus',
  off: 'Asset values are off on this hub',
  error: 'Asset values unavailable: the hub could not read them',
};

/** The header line: the connection first, then, once connected, the hub's own asset state. */
function feedWord(feed: FeedState, assets: AssetsState | undefined): string {
  if (feed === 'live' && assets && assets !== 'ready') return ASSETS_WORD[assets];
  return FEED_WORD[feed];
}

export function MapScreen() {
  const { token, api, mock } = useSignedIn();
  const hub = useHub();
  const sdk = useGateway(token);
  const sites = usePoll(() => (mock ? Promise.resolve([] as GeoSite[]) : viaSdk(() => sdk.call<GeoSite[]>({ method: 'GET', path: '/v1/sites' }))), 60_000);
  const packs = usePoll(() => (mock ? Promise.resolve(undefined) : viaSdk(() => sdk.call<Packs>({ method: 'GET', path: '/v1/map/packs' }))), 300_000);
  const machines = usePoll(async () => (api.machines ? api.machines() : ([] as MachineRecord[])), 15_000);
  const { values, feed, assets } = useAssetStream(sdk, !mock);
  const pro = useShell().view === 'pro';

  const [siteId, setSiteId] = useState<string>();
  const [floor, setFloor] = useState<string>();
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [states, setStates] = useState<ReadonlySet<Freshness>>(new Set());
  const [view, setView] = useState<View>('plan');
  const [selected, setSelected] = useState<string>();

  const site = sites.data?.find((s) => s.id === siteId) ?? sites.data?.[0];
  const all = useMemo(() => mapItems({
    now: hub.now, nodes: hub.nodes.data ?? [], nodeStatus: hub.nodeStatus, hubNodeId: hub.instance.data?.hub_node_id,
    machines: machines.data ?? [], assets: values, site,
  }), [hub.now, hub.nodes.data, hub.nodeStatus, hub.instance.data, machines.data, values, site]);

  const layers = useMemo(() => {
    const byLayer = new Map<string, number>();
    for (const it of all) byLayer.set(it.layer, (byLayer.get(it.layer) ?? 0) + 1);
    return [...byLayer].sort(([a], [b]) => (a === 'node' ? -1 : b === 'node' ? 1 : a === 'machine' ? -1 : b === 'machine' ? 1 : a.localeCompare(b)));
  }, [all]);
  const shown = all.filter((it) => !hidden.has(it.layer) && (states.size === 0 || states.has(it.state)));
  const onPlan = shown.filter((it) => it.place && (!floor || it.place.frame === floor));
  const shelf = shown.filter((it) => !it.place);
  const filteredOut = all.length - shown.length;
  const otherFloors = floor ? shown.filter((it) => it.place && it.place.frame !== floor).length : 0;
  const tally = counts(all);
  const current = all.find((it) => it.key === selected);
  const toggle = <T,>(set: ReadonlySet<T>, v: T) => { const n = new Set(set); if (n.has(v)) n.delete(v); else n.add(v); return n; };
  const loading = hub.nodes.data === undefined && !hub.nodes.error;
  // "Nothing reported" is said only when it is known: the feed delivered a complete snapshot from a ready hub
  // and the node list was read. Otherwise the screen says what it is still waiting for, or what failed.
  const knownEmpty = !hub.nodes.error && feed === 'live' && assets === 'ready';
  const nothingYet = (): string => {
    if (knownEmpty) return 'No assets yet. Nodes, machines and devices appear here as soon as they report.';
    if (hub.nodes.error) return `Could not read the nodes: ${hub.nodes.error.message}`;
    if (feed === 'off') return 'No live feed in demo mode, so no asset values.';
    if (feed === 'connecting' || feed === 'reconnecting') return 'Waiting for the live feed before saying what is here.';
    if (feed === 'denied' || feed === 'unavailable') return `${FEED_WORD[feed]}.`;
    return `${assets && assets !== 'ready' ? ASSETS_WORD[assets] : 'The hub did not say whether asset values are available'}.`;
  };

  return (
    <div className="dash-map">
      <PageHeader title="Map" lede={<>
        {site ? site.name : 'No place drawn yet'} · {all.length} {all.length === 1 ? 'item' : 'items'}
        {' · '}<span className={`dash-map-feed dash-map-feed-${feed === 'live' && assets && assets !== 'ready' ? 'unavailable' : feed}`} role="status">{feedWord(feed, assets)}</span>
      </>} actions={
        <div className="dash-map-views" role="group" aria-label="View">
          {(['plan', 'list'] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>{v === 'plan' ? 'Plan' : 'List'}</button>
          ))}
        </div>
      } />
      <div className={`dash-map-body${current ? ' has-card' : ''}`}>
        <aside className="dash-map-rail" aria-label="Places, layers and states">
          {sites.data && sites.data.length > 1 && (
            <label className="dash-map-site">Place
              <select value={site?.id} onChange={(e) => { setSiteId(e.target.value); setFloor(undefined); }}>
                {sites.data.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
          )}
          {site && (
            <section>
              <h2>Floors and areas</h2>
              <ul className="dash-map-floors">
                <li><button type="button" aria-pressed={!floor} onClick={() => setFloor(undefined)}>{site.name}<span>{all.filter((it) => it.place).length}</span></button></li>
                {(site.floors ?? []).map((f) => (
                  <li key={f.id}>
                    <button type="button" aria-pressed={floor === f.id} onClick={() => setFloor(f.id)}>{f.name}<span>{all.filter((it) => it.place?.frame === f.id).length}</span></button>
                    {(site.areas ?? []).filter((a) => a.floor_id === f.id).map((a) => <p key={a.id} className="dash-map-area">{a.name}</p>)}
                  </li>
                ))}
                {(site.areas ?? []).filter((a) => !a.floor_id).map((a) => <li key={a.id}><p className="dash-map-area">{a.name}</p></li>)}
              </ul>
            </section>
          )}
          <section>
            <h2>Layers</h2>
            {layers.length === 0 ? <p className="om-note">{knownEmpty ? 'Nothing has reported yet.' : nothingYet()}</p> : (
              <ul className="dash-map-layers">
                {layers.map(([layer, n]) => (
                  <li key={layer}>
                    <label>
                      <input type="checkbox" role="switch" checked={!hidden.has(layer)} onChange={() => setHidden(toggle(hidden, layer))} />
                      {layerName(layer)} <span>{n}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <p className="om-note dash-map-base">{baseMapNote(packs.data, packs.error?.status)}</p>
          </section>
          <section>
            <h2>State</h2>
            <div className="dash-map-states">
              {(['live', 'stale', 'offline', 'unknown'] as const).filter((s) => s !== 'unknown' || tally.unknown > 0).map((s) => (
                <button key={s} type="button" aria-pressed={states.has(s)} className={`dash-map-state is-${s}`} onClick={() => setStates(toggle(states, s))}>
                  <StatusGlyph kind={FRESHNESS_GLYPH[s]} size={14} /> {STATE_WORD[s]} {tally[s]}
                </button>
              ))}
            </div>
            <p className="om-note">Each item counts once. The shape tells the state, not only the colour.</p>
          </section>
        </aside>

        <section className="dash-map-main" aria-label={view === 'plan' ? 'Plan' : 'List'}>
          {loading ? <p role="status">Loading the box and its nodes…</p> : view === 'plan' ? (
            <>
              {site ? <Plan site={site} items={onPlan} selected={selected} onSelect={setSelected} /> : sites.error ? null : sites.data === undefined ? (
                <p role="status">Loading places…</p>
              ) : (
                <EmptyState icon="map" title="Draw your first place">
                  <p>A place is a plan in metres fixed to the earth by three surveyed points. Once one exists, everything that reports a position shows up on it. Until then, what this box knows is listed below.</p>
                </EmptyState>
              )}
              {sites.error && <p className="om-note" role="alert">Could not read places: {sites.error.message}{sites.data ? ' Showing the places last read.' : ''}</p>}
              {(filteredOut > 0 || otherFloors > 0) && (
                <p className="om-note" role="status">
                  {filteredOut > 0 && `${filteredOut} hidden by the layer and state filters. `}
                  {otherFloors > 0 && `${otherFloors} placed on other floors.`}
                </p>
              )}
              <section className="dash-map-shelf" aria-label="Not on the plan yet">
                <h2>Not on the plan yet <span>{shelf.length}</span></h2>
                {shelf.length === 0 ? <p className="om-note">{all.length === 0 ? nothingYet() : filteredOut > 0 ? 'Nothing unplaced passes the filters.' : 'Everything shown is placed.'}</p> : (
                  <ul>{shelf.map((it) => <li key={it.key}><Marker item={it} selected={selected === it.key} onSelect={setSelected} /></li>)}</ul>
                )}
              </section>
            </>
          ) : (
            <ItemList items={shown} empty={all.length === 0 ? nothingYet() : 'Nothing passes the layer and state filters.'} selected={selected} onSelect={setSelected} />
          )}
        </section>

        {current && <AssetCard item={current} pro={pro} onClose={() => setSelected(undefined)} />}
      </div>
    </div>
  );
}

function baseMapNote(packs: Packs | undefined, status: number | undefined): string {
  if (status === 503) return 'Base map: off. Offline maps are not set up on this box.';
  if (!packs) return 'Base map: off. The plan is drawn from your own place.';
  const n = packs.packs.length;
  return n === 0 ? 'Base map: off. No offline map packs are installed.' : `Base map: off. ${n} offline map ${n === 1 ? 'pack' : 'packs'} installed (${packs.packs.map((p) => p.region).join(', ')}); drawing them on the plan comes next.`;
}

function Marker({ item, selected, onSelect, style }: { item: MapItem; selected: boolean; onSelect: (k: string) => void; style?: CSSProperties }) {
  return (
    <button type="button" className={`dash-map-marker is-${item.state}${item.simulated ? ' is-simulated' : ''}${item.box ? ' is-box' : ''}`}
      aria-pressed={selected} style={style} onClick={() => onSelect(item.key)}>
      <StatusGlyph kind={FRESHNESS_GLYPH[item.state]} size={14} />
      <span className="dash-map-label" data-map-label="">{labelOf(item)}</span>
      {item.simulated && <span className="dash-map-tag">simulated</span>}
      <span className="om-visually-hidden">, {STATE_WORD[item.state]}</span>
    </button>
  );
}

function Plan({ site, items, selected, onSelect }: { site: GeoSite; items: MapItem[]; selected?: string; onSelect: (k: string) => void }) {
  const b = planBounds(site, items);
  const w = b.maxX - b.minX, h = b.maxY - b.minY;
  const step = gridStep(Math.max(w, h));
  const lines: number[] = [];
  for (let v = Math.ceil(b.minX / step) * step; v <= b.maxX; v += step) lines.push(v);
  const rows: number[] = [];
  for (let v = Math.ceil(b.minY / step) * step; v <= b.maxY; v += step) rows.push(v);
  // North up: y grows northwards in the site frame and downwards on screen.
  const left = (x: number) => `${((x - b.minX) / w) * 100}%`;
  const top = (y: number) => `${((b.maxY - y) / h) * 100}%`;
  return (
    <div className="dash-map-plan" role="region" aria-label={`Plan of ${site.name}`}>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
        {lines.map((x) => <line key={`x${x}`} x1={x - b.minX} x2={x - b.minX} y1={0} y2={h} />)}
        {rows.map((y) => <line key={`y${y}`} y1={b.maxY - y} y2={b.maxY - y} x1={0} x2={w} />)}
      </svg>
      {site.anchors.map((a, i) => <span key={i} className="dash-map-anchor" style={{ left: left(a.x), top: top(a.y) }} title="Surveyed point" data-no-value="" />)}
      {items.map((it) => <Marker key={it.key} item={it} selected={selected === it.key} onSelect={onSelect} style={{ left: left(it.place!.x), top: top(it.place!.y) }} />)}
      <span className="dash-map-north" aria-label="North is up">N ↑</span>
      <span className="dash-map-scale">Grid {step} m</span>
      {items.length === 0 && <p className="dash-map-plan-empty om-note">Nothing on this plan reports a position yet.</p>}
    </div>
  );
}

function ItemList({ items, empty, selected, onSelect }: { items: MapItem[]; empty: string; selected?: string; onSelect: (k: string) => void }) {
  if (items.length === 0) return <p className="om-note">{empty}</p>;
  return (
    <table className="dash-map-list">
      <thead><tr><th scope="col">Name</th><th scope="col">Layer</th><th scope="col">State</th><th scope="col">Value</th><th scope="col">Age</th><th scope="col">Place</th></tr></thead>
      <tbody>
        {items.map((it) => (
          <tr key={it.key} className={selected === it.key ? 'is-selected' : undefined}>
            <th scope="row"><button type="button" onClick={() => onSelect(it.key)}>{it.name}</button></th>
            <td>{layerName(it.layer)}</td>
            <td><StatusGlyph kind={FRESHNESS_GLYPH[it.state]} size={14} /> {STATE_WORD[it.state]}</td>
            <td>{it.value ?? '—'}</td>
            <td>{shortAge(it.age)}</td>
            <td>{it.place ? `${it.place.x.toFixed(1)} m, ${it.place.y.toFixed(1)} m` : 'Not placed'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AssetCard({ item, pro, onClose }: { item: MapItem; pro: boolean; onClose: () => void }) {
  return (
    <aside className="dash-map-card" aria-label={`${item.name} details`}>
      <header>
        <h2>{item.name}</h2>
        <button type="button" className="dash-map-close" aria-label="Close details" onClick={onClose}>×</button>
      </header>
      <p className="om-note">{layerName(item.layer)}{item.box ? ' · the box' : ''}{item.node ? ` · on ${item.node}` : ''}</p>
      <p className={`dash-map-state is-${item.state}`}>
        <StatusGlyph kind={FRESHNESS_GLYPH[item.state]} size={14} /> {STATE_WORD[item.state]} · {shortAge(item.age)}
        {item.simulated && <span className="dash-map-tag">simulated</span>}
      </p>
      {item.fields.length > 0 && (
        <dl className="dash-map-fields">
          {item.fields.map((f, i) => (
            <div key={`${f.field}${i}`}><dt>{f.field}</dt><dd>{f.value} · {shortAge(f.age)}{f.quality === 'simulated' ? ' · simulated' : ''}</dd></div>
          ))}
        </dl>
      )}
      <p>{item.place ? `Placed at ${item.place.x.toFixed(1)} m east, ${item.place.y.toFixed(1)} m north on ${item.place.frame}.` : `Not on the plan yet. ${item.unplaced ?? ''}`}</p>
      <p className="om-note">Read only. The Map never moves anything; changes are requests that wait in Approvals for a person.</p>
      {/* Nodes and Machines are Pro screens (shell/roles.ts): no link a guest or child would only bounce off. */}
      {item.link && pro && <Link to={item.link}>{item.kind === 'machine' ? 'Open Machines' : item.kind === 'node' ? 'Open Nodes' : 'Open'}</Link>}
    </aside>
  );
}
