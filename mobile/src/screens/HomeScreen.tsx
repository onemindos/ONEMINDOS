// SPDX-License-Identifier: Apache-2.0
import { useNavigation } from '@react-navigation/native';
import { Image, Pressable, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Polyline } from 'react-native-svg';
import { OP, sdkOf } from '../api/client';
import type { NodeStatus } from '../api/types';
import { useHubData, useNow } from '../data';
import { HEALTH_TONE, HEALTH_WORD, LIVE_WORD, healthRows, liveIndicator, type HealthTarget } from '../lib/health';
import { actionTitle, isPending, principalLabel, sortByRecent } from '../lib/approvals';
import { effectiveStatus, formatAgo, formatIn, secondsSince, STALE_AFTER_S } from '../lib/time';
import { requiresHold } from '../ui/HoldButton';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Badge, Button, Card, Loading, P, Screen, s } from '../ui/bits';
import { font, space, touchTarget, useIsDark, useTheme } from '../ui/theme';

/** Health at a glance from `GET /v1/status`: one row per source, an unknown source is never shown as ok. */
export function HealthCard() {
  const t = useTheme();
  const nav = useNavigation();
  const now = useNow();
  const { status, statusAt, statusError, hubOffsetMs, live } = useHubData();
  if (!status && !statusError) return null;
  const go = (to: HealthTarget) => ('tab' in to ? nav.navigate('Tabs', { screen: to.tab }) : nav.navigate(to.screen));
  const rows = status ? healthRows(status, now, hubOffsetMs) : [];
  const indicator = liveIndicator(live);
  return (
    <Card testID="health-card">
      <View style={s.row}>
        <Text style={{ color: t.text, fontSize: 17, fontWeight: '600' }}>Health</Text>
        <View style={s.wrap}>
          <Badge label={HEALTH_WORD[status?.state ?? 'unknown']} tone={HEALTH_TONE[status?.state ?? 'unknown']} />
          <View testID="live-indicator" accessibilityLabel={`Updates: ${LIVE_WORD[indicator]}`}>
            <Badge label={LIVE_WORD[indicator]} tone={indicator === 'live' ? 'ok' : indicator === 'reconnecting' ? 'warn' : 'neutral'} />
          </View>
        </View>
      </View>
      {statusError && (
        <View testID="health-error">
          <P muted small>
            {status && statusAt
              ? `Could not refresh health. Showing the last answer, read ${formatAgo(secondsSince(new Date(statusAt).toISOString(), now))}.`
              : 'Could not read health from the box.'}
          </P>
        </View>
      )}
      {rows.map((r) => (
        <Pressable key={r.source} accessibilityRole="button" testID={`health-${r.source}`} onPress={() => go(r.to)} style={{ minHeight: touchTarget }}>
          <View style={s.row}>
            <Text style={{ color: t.text }}>{r.label}</Text>
            <Badge label={HEALTH_WORD[r.state]} tone={HEALTH_TONE[r.state]} />
          </View>
          <P muted small>
            {r.summary ? `${r.summary} · ` : ''}read {r.age}
          </P>
        </Pressable>
      ))}
    </Card>
  );
}

const MARK = {
  light: require('../../assets/brand/mark-color-256.png'),
  dark: require('../../assets/brand/mark-on-dark-256.png'),
};

const machineStatus = {
  online: ['●', 'fresh', 'ok'],
  stale: ['◐', 'stale', 'warn'],
  offline: ['⊘', 'offline', 'neutral'],
} as const;

const appStatus = {
  healthy: ['●', 'Healthy', 'ok'],
  starting: ['◐', 'Starting', 'warn'],
  stopped: ['⊘', 'Stopped', 'neutral'],
  unhealthy: ['▲', 'Unhealthy', 'bad'],
} as const;

function LiveTemperature({ nodeId, name, now }: { nodeId: string; name: string; now: number }) {
  const { api } = useSignedIn();
  const { fetchedAt } = useHubData();
  const t = useTheme();
  const { data, error } = useLoad(() => api.nodeMetrics(nodeId, '5m'), [api, nodeId, fetchedAt]);
  const samples = (data?.samples ?? [])
    .flatMap(({ at, temp_c }) => typeof temp_c === 'number' && Number.isFinite(temp_c) && Number.isFinite(Date.parse(at))
      ? [{ at, value: temp_c }] : [])
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  const latest = samples.at(-1);
  const age = latest ? secondsSince(latest.at, now) : null;
  if (error || !latest || age === null || age >= STALE_AFTER_S) return null;

  const values = samples.map((p) => p.value);
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const start = Date.parse(samples[0]!.at);
  const duration = Date.parse(latest.at) - start;
  const points = samples.map((p) => `${duration ? (Date.parse(p.at) - start) * 98 / duration + 1 : 1},${25 - (p.value - min) * 22 / span}`);
  return (
    <Card testID="live-temperature">
      <P small>{name} · temperature</P>
      <View style={s.row}>
        <Text style={{ color: t.text, fontWeight: font.bold, fontSize: 28, fontVariant: ['tabular-nums'] }}>{latest.value.toFixed(1)} °C</Text>
        <P muted small>● Live · {formatAgo(age)}</P>
      </View>
      {duration > 0 && <Svg width="100%" height={26} viewBox="0 0 100 26" preserveAspectRatio="none" accessible={false}>
        <Polyline points={points.join(' ')} fill="none" stroke={t.action} strokeWidth={1.5} />
      </Svg>}
    </Card>
  );
}

function InstalledTile({ id, name, now }: { id: string; name: string; now: number }) {
  const nav = useNavigation();
  const { api, features } = useSignedIn();
  const { fetchedAt } = useHubData();
  const t = useTheme();
  const sdk = sdkOf(api);
  const available = features.has('GET /v1/apps/{}');
  const { data } = useLoad(async () => {
    if (!sdk || !available) return undefined;
    const detail = await sdk.call<unknown>({ method: 'GET', path: `/v1/apps/${encodeURIComponent(id)}` });
    if (!detail || typeof detail !== 'object' || !('health' in detail)) return undefined;
    const health = detail.health;
    if (!health || typeof health !== 'object' || !('state' in health) || !('checked_at' in health) ||
        typeof health.state !== 'string' || typeof health.checked_at !== 'string') return undefined;
    const entry = Object.entries(appStatus).find(([state]) => state === health.state)?.[1];
    return entry && { entry, checkedAt: health.checked_at };
  }, [id, sdk, available, fetchedAt]);
  const age = data && secondsSince(data.checkedAt, now);
  return (
    <Pressable style={{ flex: 1, minWidth: 64, alignItems: 'center', gap: 4 }} accessibilityRole="button"
      onPress={() => nav.navigate('AppDetail', { id })}>
      <View style={{ width: 52, height: 52, borderRadius: 16, backgroundColor: t.raised, borderColor: t.border, borderWidth: 1, alignItems: 'center', justifyContent: 'center' }}>
        <Text accessibilityElementsHidden importantForAccessibility="no" style={{ color: t.text, fontSize: 21 }}>▦</Text>
      </View>
      <Text style={{ color: t.text, fontSize: font.xs, textAlign: 'center', fontWeight: font.semibold }}>{name}</Text>
      {data && age != null && <Text style={{ color: t[data.entry[2]], fontSize: font.xs, textAlign: 'center' }}>
        {data.entry[0]} {data.entry[1]}{'\n'}{formatAgo(age)}
      </Text>}
    </Pressable>
  );
}

export function HomeScreen() {
  const t = useTheme();
  const dark = useIsDark();
  const nav = useNavigation();
  const now = useNow();
  const { me, features } = useSignedIn();
  const { instance, nodes, apps, actions, fetchedAt, hubOffsetMs, loading } = useHubData();
  const hubTime = now + (hubOffsetMs ?? 0);
  const profileName = me && 'display_name' in me && typeof me.display_name === 'string' ? me.display_name.trim() : '';
  const name = profileName || me?.principal.display_name?.trim();
  const pending = sortByRecent((actions ?? []).filter(isPending));
  const first = pending[0];
  const expiry = first ? formatIn(first.expires_at, hubTime) : null;
  const installed = (apps ?? []).filter((a) => a.installed).slice(0, 4);
  const counts: Record<NodeStatus, number> = { online: 0, stale: 0, offline: 0 };
  for (const n of nodes ?? []) counts[effectiveStatus(n.status, n.last_seen, now, { fetchedAt, hubOffsetMs })]++;
  const hub = nodes?.find((n) => n.node_id === instance?.hub_node_id);
  const hour = new Date(now).getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  if (loading && !instance) return <Loading what="your hub" />;
  return (
    <SafeAreaView edges={['top']} style={{ flex: 1 }}>
      <Screen testID="home">
        <View style={[s.row, { alignItems: 'center' }]}>
          <View style={[s.wrap, { flex: 1 }]}>
            <Image source={dark ? MARK.dark : MARK.light} style={{ width: 24, height: 24 }} />
            <P>{instance?.name ?? 'OneMind'}</P>
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Me" onPress={() => nav.navigate('Tabs', { screen: 'Me' })}
            style={{ width: touchTarget, minHeight: touchTarget, alignItems: 'center', justifyContent: 'center' }}>
            <View style={{ backgroundColor: t.raised, borderRadius: 18, width: 34, height: 34, alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ color: t.text, fontWeight: font.bold, fontSize: font.sm }}>{name ? Array.from(name)[0]?.toLocaleUpperCase() : '♙'}</Text>
            </View>
          </Pressable>
        </View>
        <Text accessibilityRole="header" style={{ color: t.text, fontSize: 26, fontWeight: font.bold }}>{greeting}{name ? `, ${name}` : ''}.</Text>
        {actions && <P muted small>{pending.length === 1 ? '1 request needs a decision.' : `${pending.length} requests need a decision.`}</P>}
        {first && (
          <Card testID="pending-card">
            <View style={s.row}>
              <Text style={{ color: t.bad, fontWeight: font.bold, fontSize: font.sm }}>◆ Needs you</Text>
              {pending.length > 1 && <P muted small>1 of {pending.length}</P>}
            </View>
            <P muted small>{principalLabel(first.requested_by)}{expiry === 'unknown' ? '' : expiry === 'expired' ? ' · expired' : ` · expires ${expiry}`}</P>
            <Text style={{ color: t.text, fontSize: 20, fontWeight: font.bold }}>{first.plan?.summary || actionTitle(first)}</Text>
            <Button testID="review-first" label="Review and decide" onPress={() => nav.navigate('Tabs', { screen: 'Approvals', params: { id: first.id } })} />
            {requiresHold(first) &&
              <P muted small>Hold to approve on the next screen, then sign.</P>}
          </Card>
        )}
        {!!installed.length && <View style={s.row}>
          {installed.map((a) => <InstalledTile key={a.id} id={a.id} name={a.name} now={hubTime} />)}
        </View>}
        {hub && features.has(OP.nodeMetrics) && <LiveTemperature key={hub.node_id} nodeId={hub.node_id} name={hub.hostname ?? hub.node_id} now={hubTime} />}
        {nodes && <Pressable accessibilityRole="button" onPress={() => nav.navigate('Nodes')}>
          <Card>
            <View style={s.row}><P>Machines</P><P muted>›</P></View>
            <View style={s.wrap}>
              {(['online', 'stale', 'offline'] as const).map((status) => {
                const [shape, label, tone] = machineStatus[status];
                return <Badge key={status} label={`${shape} ${counts[status]} ${label}`} tone={tone} />;
              })}
            </View>
            {fetchedAt && <P muted small>Checked {formatAgo(Math.max(0, Math.floor((now - fetchedAt) / 1000)))}</P>}
          </Card>
        </Pressable>}
      </Screen>
    </SafeAreaView>
  );
}
