// SPDX-License-Identifier: Apache-2.0
import { useNavigation } from '@react-navigation/native';
import { Pressable, Text, View } from 'react-native';
import type { NodeStatus } from '../api/types';
import { useHubData, useNow } from '../data';
import { actionTitle, principalLabel, sortByRecent } from '../lib/approvals';
import { effectiveStatus, formatAgo, secondsSince } from '../lib/time';
import { usePhotoBackup } from '../photos/context';
import { summarize } from '../photos/status';
import { useSignedIn } from '../session';
import { Badge, Card, H1, H2, Loading, P, Row, Screen, STATUS_TONE, StateBadge, s } from '../ui/bits';
import { space, useTheme } from '../ui/theme';

export function HomeScreen() {
  const t = useTheme();
  const nav = useNavigation();
  const now = useNow();
  const { label } = useSignedIn();
  const { instance, nodes, apps, actions, fetchedAt, hubOffsetMs, pendingCount, loading } = useHubData();
  const photos = usePhotoBackup();
  if (loading && !instance) return <Loading what="your hub" />;

  const counts: Record<NodeStatus, number> = { online: 0, stale: 0, offline: 0 };
  for (const n of nodes ?? []) counts[effectiveStatus(n.status, n.last_seen, now, { fetchedAt, hubOffsetMs })]++;
  const installed = (apps ?? []).filter((a) => a.installed);
  const recent = sortByRecent(actions ?? []).slice(0, 3);

  return (
    <Screen testID="home">
      <View>
        <H1>{instance?.name ?? 'OneMind'}</H1>
        <P muted small>
          {label} · version {instance?.version ?? 'unknown'} · hub node {instance?.hub_node_id ?? 'unknown'}
        </P>
      </View>

      <Pressable accessibilityRole="button" onPress={() => nav.navigate('Tabs', { screen: 'Approvals' })}>
        <Card testID="pending-card">
          <View style={s.row}>
            <Text style={{ color: t.text, fontSize: 17, fontWeight: '600' }}>Approvals</Text>
            <Badge label={pendingCount ? `${pendingCount} waiting` : 'none waiting'} tone={pendingCount ? 'info' : 'neutral'} />
          </View>
          <P muted small>
            {pendingCount
              ? 'Something is asking to change your OneMind. Nothing happens until an owner says yes.'
              : 'No change is waiting for a decision.'}
          </P>
        </Card>
      </Pressable>

      <Pressable accessibilityRole="button" onPress={() => nav.navigate('Nodes')}>
        <Card>
          <View style={s.row}>
            <Text style={{ color: t.text, fontSize: 17, fontWeight: '600' }}>Nodes</Text>
            <Text style={{ color: t.muted }}>{(nodes ?? []).length} total</Text>
          </View>
          <View style={s.wrap}>
            {(['online', 'stale', 'offline'] as const).map((k) => (
              <Badge key={k} label={`${counts[k]} ${k}`} tone={counts[k] ? STATUS_TONE[k] : 'neutral'} />
            ))}
          </View>
        </Card>
      </Pressable>

      <Pressable accessibilityRole="button" onPress={() => nav.navigate('PhotoBackup')} testID="photos-card">
        <Card>
          <View style={s.row}>
            <Text style={{ color: t.text, fontSize: 17, fontWeight: '600' }}>Photo backup</Text>
            <Text style={{ color: t.muted }}>›</Text>
          </View>
          <P muted small>{summarize({ ...photos, now }).headline}</P>
        </Card>
      </Pressable>

      <H2>Installed apps ({installed.length})</H2>
      <Card>
        {installed.length === 0 ? (
          <P muted>No apps installed yet.</P>
        ) : (
          installed.map((a) => (
            <Pressable key={a.id} onPress={() => nav.navigate('AppDetail', { id: a.id })} accessibilityRole="button">
              <Row label={a.name} value={`${a.version} · ${a.status.replace(/_/g, ' ')}`} />
            </Pressable>
          ))
        )}
      </Card>

      <H2>Recent activity</H2>
      <Card>
        {recent.length === 0 ? (
          <P muted>Nothing yet.</P>
        ) : (
          recent.map((a) => (
            <View key={a.id} style={{ gap: space.xs }}>
              <View style={s.row}>
                <Text style={{ color: t.text, fontWeight: '600' }}>{actionTitle(a)}</Text>
                <StateBadge state={a.state} />
              </View>
              <P muted small>
                {principalLabel(a.requested_by)} ·{' '}
                {formatAgo(secondsSince(a.updated_at ?? a.created_at ?? '', now + (hubOffsetMs ?? 0)))}
              </P>
            </View>
          ))
        )}
      </Card>
    </Screen>
  );
}
