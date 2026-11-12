// SPDX-License-Identifier: Apache-2.0
import { useNavigation } from '@react-navigation/native';
import { Pressable, Text, View } from 'react-native';
import type { AppTier, CatalogApp } from '../api/types';
import { useHubData } from '../data';
import { formatDay, installBlockReason } from '../lib/scan';
import { Badge, Card, H1, H2, Loading, P, Screen, s } from '../ui/bits';
import { useTheme } from '../ui/theme';

export const TIER_TONE: Record<AppTier, 'ok' | 'neutral' | 'bad'> = { verified: 'ok', community: 'neutral', blocked: 'bad' };

export function scanLabel(app: CatalogApp): { text: string; tone: 'ok' | 'warn' | 'bad' } {
  if (!app.scan) return { text: 'not scanned', tone: 'warn' };
  if (app.scan.result !== 'pass') return { text: `scan failed ${formatDay(app.scan.scanned_at)}`, tone: 'bad' };
  return { text: `scanned ${formatDay(app.scan.scanned_at)}`, tone: 'ok' };
}

function AppRow({ app, hubNow }: { app: CatalogApp; hubNow: number }) {
  const t = useTheme();
  const nav = useNavigation();
  const scan = scanLabel(app);
  const blocked = !app.installed && installBlockReason(app, hubNow);
  return (
    <Pressable accessibilityRole="button" onPress={() => nav.navigate('AppDetail', { id: app.id })}>
      <Card testID={`app-${app.id}`}>
        <View style={s.row}>
          <Text style={{ color: t.text, fontSize: 17, fontWeight: '600' }}>{app.name}</Text>
          <Text style={{ color: t.muted }}>{app.version}</Text>
        </View>
        <P muted small>{app.description}</P>
        <View style={s.wrap}>
          {app.installed && <Badge label={app.status.replace(/_/g, ' ')} tone="info" />}
          <Badge label={app.tier ?? 'no tier'} tone={app.tier ? TIER_TONE[app.tier] : 'warn'} />
          <Badge label={scan.text} tone={scan.tone} />
          <Badge label={app.license} />
          {blocked ? <Badge label="cannot install yet" tone="warn" /> : null}
        </View>
      </Card>
    </Pressable>
  );
}

export function AppsScreen() {
  const { apps, hubOffsetMs, loading } = useHubData();
  if (loading && !apps) return <Loading what="apps" />;
  const hubNow = Date.now() + (hubOffsetMs ?? 0);
  const installed = (apps ?? []).filter((a) => a.installed);
  const available = (apps ?? []).filter((a) => !a.installed);
  return (
    <Screen testID="apps">
      <H1>Apps</H1>
      <P muted small>Only apps with a passing security scan from the last 7 days can be installed. Every install waits for an owner.</P>
      {installed.length > 0 && <H2>Installed</H2>}
      {installed.map((a) => (
        <AppRow key={a.id} app={a} hubNow={hubNow} />
      ))}
      <H2>Available</H2>
      {available.length === 0 ? <P muted>Everything in the catalog is installed.</P> : available.map((a) => <AppRow key={a.id} app={a} hubNow={hubNow} />)}
    </Screen>
  );
}
