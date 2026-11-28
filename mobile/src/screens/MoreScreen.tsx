// SPDX-License-Identifier: Apache-2.0
// Atlas Me collects account, activity and management screens.
import { SafeAreaView } from 'react-native-safe-area-context';
import { HealthCard } from './HomeScreen';
import { useNavigation } from '@react-navigation/native';
import { Pressable, Text, View } from 'react-native';
import type { RootParams } from '../nav';
import { OP } from '../api/client';
import { useHubData } from '../data';
import { useSignedIn } from '../session';
import { Badge, Card, H1, H2, Screen, s } from '../ui/bits';
import { font, useTheme } from '../ui/theme';

type Target = Exclude<keyof RootParams, 'Tabs' | 'AppDetail' | 'PhotoAlbums'>;

function Item({ label, detail, to, badge }: { label: string; detail: string; to: Target; badge?: number }) {
  const t = useTheme();
  const nav = useNavigation();
  return (
    <Pressable testID={`more-${to}`} accessibilityRole="button" accessibilityLabel={badge ? `${label}, ${badge} new` : label} onPress={() => nav.navigate(to as never)}>
      {({ pressed }) => (
        <Card>
          <View style={[s.row, { opacity: pressed ? 0.85 : 1 }]}>
            <View style={{ flexShrink: 1, gap: 2 }}>
              <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold }}>{label}</Text>
              <Text style={{ color: t.muted, fontSize: font.sm }}>{detail}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              {badge ? <Badge label={String(badge)} tone="info" /> : null}
              <Text style={{ color: t.muted, fontSize: font.lg }}>›</Text>
            </View>
          </View>
        </Card>
      )}
    </Pressable>
  );
}

export function MoreScreen() {
  const { unreadCount, alerts } = useHubData();
  const open = (alerts ?? []).filter((a) => a.state === 'open').length;
  const { features } = useSignedIn();
  return (
    <SafeAreaView edges={['top']} style={{ flex: 1 }}>
      <Screen testID="more">
        <H1>Me</H1>
        <Item to="Settings" label="Settings" detail="You, this phone, push, connection" />
        <Item to="Permissions" label="This phone" detail="Permissions and why OneMind asks for them" />
        <Item to="Activity" label="Activity" detail="Requests, decisions and results" />
        <Item to="Inbox" label="Inbox" detail="Alerts and notifications from your box" badge={unreadCount + open || undefined} />
        <Item to="Nodes" label="Nodes" detail="Every machine in your OneMind, and whether it is live" />
        {features.has(OP.backupStatus) && <Item to="Backups" label="Backups" detail="Is your box protected, and ask for a backup" />}
        {features.has(OP.automationRules) && <Item to="Automation" label="Automation" detail="Rules, pause and what fired" />}
        {features.has(OP.filesRoots) && <Item to="Files" label="Files" detail="Browse what the box shares with you" />}
        {features.has(OP.migratePlans) && <Item to="Migrate" label="Migration" detail="Plans to move apps from another cluster" />}
        {features.has(OP.users) && <Item to="People" label="People" detail="Family roles: owner, adult, teen, child, guest" />}
        {features.has(OP.killSwitch) && <Item to="Agents" label="Agents" detail="What AI agents may do, asked and the stop switch" />}
        {(features.source !== 'openapi' || features.has(OP.tips)) && (
          <Item to="Tips" label="Tips" detail="Short guides to your OneMind" />
        )}
        <H2>System</H2>
        {features.has(OP.osUpdates) && <Item to="OsUpdates" label="OS updates" detail="Running version, update on offer, ask to install" />}
        {features.has(OP.systemPlan) && <Item to="SystemControls" label="System controls" detail="Restart, shut down or troubleshoot, as a request" />}
        <Item to="DeviceInfo" label="About this box" detail="Hardware, system version, uptime" />
        {(features.has(OP.nodeMetrics) || features.has(OP.appMetrics) || features.has(OP.monitoringSummary)) && (
          <Item to="LiveUsage" label="Live usage" detail="CPU, memory and disk, per machine and per app" />
        )}
        {features.has(OP.mesh) && <Item to="Network" label="Network" detail="Box names and HTTPS, read only" />}
        <Item to="PhotoBackup" label="Photo backup" detail="This phone's photos to your box" />
        <HealthCard />
      </Screen>
    </SafeAreaView>
  );
}

/** Badge for the More tab: what is waiting behind it. */
export function useMoreBadge(): number | undefined {
  const { unreadCount, alerts } = useHubData();
  const n = unreadCount + (alerts ?? []).filter((a) => a.state === 'open').length;
  return n || undefined;
}
