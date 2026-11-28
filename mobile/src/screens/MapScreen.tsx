// SPDX-License-Identifier: Apache-2.0
// Phone Map tab (#656), Atlas design 13b: sites, state filters, a plan with every asset as a live tile with its age,
// a card for the selected asset, and a list fallback. Everything comes from the hub: sites over `GET /v1/sites`, asset
// values over the `asset.*` event stream (#606). No sample data: with nothing on the box the tab says so.
import { useMemo, useState } from 'react';
import { Pressable, useWindowDimensions, Text, View } from 'react-native';
import Svg, { G, Path, Rect, Circle, Line, Text as SvgText } from 'react-native-svg';
import { OP } from '../api/client';
import type { GeoSite } from '../api/types';
import { useHubData, useNow } from '../data';
import { liveIndicator, LIVE_WORD } from '../lib/health';
import {
  ageSeconds,
  boundsOf,
  countsByFreshness,
  formatValue,
  FRESH_WORD,
  freshness,
  inBounds,
  makeProjector,
  newestField,
  positionOf,
  shortAge,
  sortedAssets,
  type Asset,
  type Freshness,
} from '../lib/map';
import { useAssets, type AssetFeed } from '../lib/useAssets';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Card, H1, H2, Loading, Notice, P, Screen } from '../ui/bits';
import { font, radius, radiusControl, space, touchTarget, useTheme, type Palette } from '../ui/theme';

const PLAN_H = 320;

function tone(t: Palette, f: Freshness) {
  return f === 'fresh' ? t.ok : f === 'stale' ? t.warn : t.neutral;
}

/** Filled circle = fresh, half ring = stale, slashed ring = offline (the design's shape rule). */
function Shape({ f, x, y, r, t }: { f: Freshness; x: number; y: number; r: number; t: Palette }) {
  const c = tone(t, f);
  if (f === 'fresh') return <Circle cx={x} cy={y} r={r} fill={c} />;
  if (f === 'stale')
    return (
      <G>
        <Circle cx={x} cy={y} r={r - 1} fill="none" stroke={c} strokeWidth={2} />
        <Path d={`M ${x - r + 1} ${y} A ${r - 1} ${r - 1} 0 0 1 ${x + r - 1} ${y} Z`} fill={c} />
      </G>
    );
  return (
    <G>
      <Circle cx={x} cy={y} r={r - 1} fill="none" stroke={c} strokeWidth={2} />
      <Line x1={x - r + 2} y1={y + r - 2} x2={x + r - 2} y2={y - r + 2} stroke={c} strokeWidth={2} />
    </G>
  );
}

function ShapeIcon({ f, size = 14 }: { f: Freshness; size?: number }) {
  const t = useTheme();
  const r = size / 2;
  return (
    <Svg width={size} height={size} accessible={false}>
      <Shape f={f} x={r} y={r} r={r} t={t} />
    </Svg>
  );
}

/** The one line a tile shows: the newest value and how old it is. */
function summary(a: Asset, now: number): string {
  const n = newestField(a);
  if (!n) return 'no value';
  return `${formatValue(n[1])} · ${shortAge(ageSeconds(n[1].time, now))}`;
}

const label = (a: Asset) => a.id;

/** The tile's words: id, newest value, age, and the state word when it is not fresh (shape and word, never colour alone). */
function tileText(a: Asset, f: Freshness, now: number): string {
  const n = newestField(a);
  return `${label(a)} · ${summary(a, now)}${f === 'fresh' ? '' : ` · ${FRESH_WORD[f]}`}${n?.[1].quality === 'simulated' ? ' · simulated' : ''}`;
}

function Chip({ text, on, onPress, testID, icon }: { text: string; on: boolean; onPress: () => void; testID?: string; icon?: Freshness }) {
  const t = useTheme();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ selected: on }}
      onPress={onPress}
      style={{
        minHeight: touchTarget,
        paddingHorizontal: space.md,
        borderRadius: radiusControl * 3,
        borderWidth: 1,
        borderColor: on ? t.accent : t.border,
        backgroundColor: on ? t.accentSoft : t.card,
        flexDirection: 'row',
        alignItems: 'center',
        gap: space.xs,
      }}
    >
      {icon && <ShapeIcon f={icon} />}
      <Text style={{ color: on ? t.accentText : t.text, fontSize: font.sm }}>{text}</Text>
    </Pressable>
  );
}

function Plan({ assets, sites, now, selected, onSelect }: { assets: Asset[]; sites: GeoSite[]; now: number; selected?: string; onSelect: (k: string) => void }) {
  const t = useTheme();
  const width = useWindowDimensions().width - 2 * space.lg;
  const placed = assets.map((a) => ({ a, p: positionOf(a) })).filter((x): x is { a: Asset; p: { lat: number; lon: number } } => !!x.p);
  const anchors = sites.flatMap((s) => s.anchors.map((x) => ({ lat: x.lat, lon: x.lon })));
  const b = boundsOf([...anchors, ...placed.map((x) => x.p)]);
  if (!b) return null;
  const project = makeProjector(b, width, PLAN_H);
  const frame = sites.map((s) => ({ s, b: boundsOf(s.anchors) })).filter((x) => !!x.b);
  return (
    <Svg testID="map-plan" width={width} height={PLAN_H} accessibilityLabel="Plan of your places and devices">
      <Rect x={0} y={0} width={width} height={PLAN_H} rx={radius} fill={t.sunken} stroke={t.border} />
      {frame.map(({ s, b: sb }) => {
        const a = project({ lat: sb!.maxLat, lon: sb!.minLon });
        const z = project({ lat: sb!.minLat, lon: sb!.maxLon });
        return (
          <G key={s.id}>
            <Rect x={a.x} y={a.y} width={Math.max(z.x - a.x, 1)} height={Math.max(z.y - a.y, 1)} fill="none" stroke={t.borderStrong} strokeDasharray="6 4" />
            <SvgText x={a.x + 6} y={a.y + 14} fill={t.muted} fontSize={font.xs}>
              {s.name}
            </SvgText>
          </G>
        );
      })}
      {placed.map(({ a, p }) => {
        const f = freshness(a, now);
        const { x, y } = project(p);
        const text = tileText(a, f, now);
        const w = Math.min(text.length * 6.4 + 12, width - 8);
        const lx = Math.min(Math.max(x - w / 2, 4), width - w - 4);
        const on = selected === a.key;
        return (
          <G key={a.key} testID={`plan-${a.key}`} accessible accessibilityRole="button" accessibilityLabel={`${a.id}, ${FRESH_WORD[f]}, ${summary(a, now)}`} onPress={() => onSelect(a.key)}>
            <Rect x={lx} y={y + 12} width={w} height={20} rx={6} fill={t.card} stroke={on ? t.accent : t.border} strokeWidth={on ? 2 : 1} />
            <SvgText x={lx + 6} y={y + 26} fill={t.text} fontSize={font.xs}>
              {text.length * 6.4 + 12 > w ? `${text.slice(0, Math.floor((w - 12) / 6.4) - 1)}…` : text}
            </SvgText>
            <Circle cx={x} cy={y} r={on ? 14 : 12} fill={t.card} stroke={on ? t.accent : t.border} strokeWidth={on ? 2 : 1} />
            <Shape f={f} x={x} y={y} r={7} t={t} />
            <Circle cx={x} cy={y} r={22} fill="transparent" />
          </G>
        );
      })}
    </Svg>
  );
}

function AssetCard({ a, now, onClose }: { a: Asset; now: number; onClose: () => void }) {
  const t = useTheme();
  const f = freshness(a, now);
  const n = newestField(a);
  const fields = Object.entries(a.fields).sort(([x], [y]) => x.localeCompare(y));
  return (
    <Card testID="asset-card">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
        <ShapeIcon f={f} size={18} />
        <View style={{ flex: 1 }}>
          <Text style={{ color: t.text, fontSize: font.lg, fontWeight: font.semibold }}>{a.id}</Text>
          <Text style={{ color: t.muted, fontSize: font.sm }}>
            {a.cls} · {FRESH_WORD[f]}
            {n ? ` · ${shortAge(ageSeconds(n[1].time, now))}` : ''}
          </Text>
        </View>
        <Chip text="Close" on={false} onPress={onClose} testID="asset-close" />
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
        {fields.map(([name, v]) => (
          <View key={name} testID={`field-${name}`} style={{ minWidth: 100, flexGrow: 1, padding: space.md, borderRadius: radiusControl, borderWidth: 1, borderColor: t.border, backgroundColor: t.sunken }}>
            <Text style={{ color: t.muted, fontSize: font.xs }}>{name}</Text>
            <Text style={{ color: t.text, fontSize: font.xl, fontWeight: font.bold, fontVariant: ['tabular-nums'] }}>{formatValue(v)}</Text>
            <Text style={{ color: t.muted, fontSize: font.xs }}>
              {shortAge(ageSeconds(v.time, now))}
              {v.quality === 'simulated' ? ' · simulated' : v.quality === 'stale' ? ' · source says stale' : ''}
            </Text>
          </View>
        ))}
      </View>
    </Card>
  );
}

function AssetRow({ a, now, on, onPress }: { a: Asset; now: number; on: boolean; onPress: () => void }) {
  const t = useTheme();
  const f = freshness(a, now);
  return (
    <Pressable
      testID={`row-${a.key}`}
      accessibilityRole="button"
      accessibilityLabel={`${a.id}, ${FRESH_WORD[f]}, ${summary(a, now)}`}
      onPress={onPress}
      style={{ minHeight: touchTarget, flexDirection: 'row', alignItems: 'center', gap: space.sm, padding: space.md, borderRadius: radiusControl, borderWidth: 1, borderColor: on ? t.accent : t.border, backgroundColor: t.card }}
    >
      <ShapeIcon f={f} />
      <View style={{ flex: 1 }}>
        <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold }}>{a.id}</Text>
        <Text style={{ color: t.muted, fontSize: font.sm }}>
          {a.cls} · {FRESH_WORD[f]}
        </Text>
      </View>
      <Text style={{ color: t.text, fontSize: font.sm, fontVariant: ['tabular-nums'] }}>{summary(a, now)}</Text>
    </Pressable>
  );
}

type Gate = 'loading' | 'empty' | 'blocked';

/** What an empty map means. "Nothing on the map yet" only when the box said its asset store is ready and the snapshot was empty. */
function gate(f: AssetFeed): Gate {
  if (f.state === 'open') {
    if (!f.ready) return 'loading';
    return f.store === 'ready' && !f.incomplete ? 'empty' : 'blocked';
  }
  return f.state === 'connecting' || f.state === 'retrying' ? 'loading' : 'blocked';
}

/** One notice for the one thing that is going on; never two contradictory cards. */
function notice(f: AssetFeed, count: number) {
  if (f.state === 'off' || f.state === 'unsupported') return <Notice tone="warn" text="This box does not stream live values, so there is nothing to draw yet." />;
  if (f.state === 'forbidden') return <Notice tone="warn" text="You are not allowed to see device values on this box. Ask the owner." />;
  if (f.state === 'unauthenticated' || f.state === 'stopped') return <Notice tone="warn" text="The phone is not connected to the box. Sign in again or check the connection." />;
  if ((f.state === 'retrying' || f.state === 'connecting') && count > 0) return <Notice tone="warn" text="Reconnecting. This is the last map the phone saw; every age keeps counting." />;
  if (f.state === 'open' && f.ready && f.store !== 'ready') {
    return <Notice tone="warn" text={f.store === 'pending' ? "The box's asset store is still starting. Values will appear when it is ready." : "The box's asset store isn't available, so the map cannot show values."} />;
  }
  if (f.state === 'open' && f.ready && f.incomplete) return <Notice tone="warn" text="Some values may be missing from this map." />;
  return null;
}

export function MapScreen() {
  const t = useTheme();
  const now0 = useNow();
  const { hubOffsetMs } = useHubData();
  const now = now0 + (hubOffsetMs ?? 0);
  const { api, features } = useSignedIn();
  const feed = useAssets();
  const sitesRes = useLoad<GeoSite[]>(() => (features.has(OP.sites) ? api.sites() : Promise.resolve([])), [api, features]);
  const [view, setView] = useState<'plan' | 'list'>('plan');
  const [siteId, setSiteId] = useState<string | undefined>();
  const [cls, setCls] = useState<string | undefined>();
  const [state, setState] = useState<Freshness | undefined>();
  const [selected, setSelected] = useState<string | undefined>();

  const sites = sitesRes.data ?? [];
  const site = sites.find((s) => s.id === siteId);
  const all = useMemo(() => sortedAssets(feed.assets), [feed.assets]);
  const classes = useMemo(() => [...new Set(all.map((a) => a.cls))], [all]);
  const siteBounds = site ? boundsOf(site.anchors) : undefined;
  const visible = all.filter((a) => {
    if (cls && a.cls !== cls) return false;
    if (state && freshness(a, now) !== state) return false;
    if (siteBounds) {
      const p = positionOf(a);
      if (!p || !inBounds(p, siteBounds, 0.0005)) return false;
    }
    return true;
  });
  const counts = countsByFreshness(all, now);
  const chosen = selected ? feed.assets[selected] : undefined;
  const ind = liveIndicator(feed.state);
  const unplaced = visible.filter((a) => !positionOf(a)).length;

  return (
    <Screen testID="map">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <H1>Map</H1>
        {feed.state !== 'off' && (
          <Text testID="map-live" style={{ color: ind === 'live' ? t.ok : t.warn, fontSize: font.sm }}>
            {LIVE_WORD[ind]}
          </Text>
        )}
      </View>

      {notice(feed, all.length)}

      {all.length === 0 ? (
        gate(feed) === 'loading' ? (
          <Loading what="the map" />
        ) : gate(feed) === 'empty' ? (
          <Card testID="map-empty">
            <H2>Nothing on the map yet</H2>
            <P muted>
              When a sensor, camera, lock or machine reports to your box it appears here with the age of its last value. Add one from Apps, or ask the box owner.
            </P>
          </Card>
        ) : null
      ) : (
        <>
          {sites.length > 0 && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
              <Chip text="All places" on={!siteId} onPress={() => setSiteId(undefined)} testID="site-all" />
              {sites.map((s) => (
                <Chip key={s.id} text={s.name} on={siteId === s.id} onPress={() => setSiteId(s.id)} testID={`site-${s.id}`} />
              ))}
            </View>
          )}
          <View style={{ flexDirection: 'row', gap: space.sm }}>
            <Chip text="Plan" on={view === 'plan'} onPress={() => setView('plan')} testID="view-plan" />
            <Chip text="List" on={view === 'list'} onPress={() => setView('list')} testID="view-list" />
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {(['fresh', 'stale', 'offline'] as const).map((f) => (
              <Chip key={f} icon={f} text={`${counts[f]} ${FRESH_WORD[f]}`} on={state === f} onPress={() => setState(state === f ? undefined : f)} testID={`state-${f}`} />
            ))}
            {classes.map((c) => (
              <Chip key={c} text={c} on={cls === c} onPress={() => setCls(cls === c ? undefined : c)} testID={`class-${c}`} />
            ))}
          </View>

          {view === 'plan' && <Plan assets={visible} sites={site ? [site] : sites} now={now} selected={selected} onSelect={setSelected} />}
          {view === 'plan' && unplaced > 0 && (
            <P muted small>
              {unplaced} without a position {unplaced === 1 ? 'is' : 'are'} only in the list.
            </P>
          )}
          {chosen && <AssetCard a={chosen} now={now} onClose={() => setSelected(undefined)} />}
          {(view === 'list' || !boundsOf(visible.flatMap((a) => positionOf(a) ?? []))) && (
            <View style={{ gap: space.sm }}>
              {visible.length === 0 ? (
                <P muted>No device matches this filter.</P>
              ) : (
                visible.map((a) => <AssetRow key={a.key} a={a} now={now} on={selected === a.key} onPress={() => setSelected(a.key)} />)
              )}
            </View>
          )}
        </>
      )}
    </Screen>
  );
}
