// SPDX-License-Identifier: Apache-2.0
// "More" (docs/design/IA.md §1, §3): what does not get a tab on a phone. Badges here sum what is hidden.
import { useNavigation } from '@react-navigation/native';
import { Pressable, Text, View } from 'react-native';
import type { RootParams } from '../nav';
import { OP } from '../api/client';
import { useHubData } from '../data';
import { useSignedIn } from '../session';
import { Badge, Card, H1, Screen, s } from '../ui/bits';
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
    <Screen testID="more">
      <H1>More</H1>
      <Item to="Inbox" label="Inbox" detail="Alerts and notifications from your box" badge={unreadCount + open || undefined} />
      <Item to="Nodes" label="Nodes" detail="Every machine in your OneMind, and whether it is live" />
      {features.has(OP.backupStatus) && <Item to="Backups" label="Backups" detail="Is your box protected, and ask for a backup" />}
      {features.has(OP.automationRules) && <Item to="Automation" label="Automation" detail="Rules, pause and what fired" />}
      {features.has(OP.filesRoots) && <Item to="Files" label="Files" detail="Browse what the box shares with you" />}
      {features.has(OP.migratePlans) && <Item to="Migrate" label="Migration" detail="Plans to move apps from another cluster" />}
      <Item to="PhotoBackup" label="Photo backup" detail="This phone's photos to your box" />
      <Item to="Settings" label="Settings" detail="You, this phone, push, connection" />
    </Screen>
  );
}

/** Badge for the More tab: what is waiting behind it. */
export function useMoreBadge(): number | undefined {
  const { unreadCount, alerts } = useHubData();
  const n = unreadCount + (alerts ?? []).filter((a) => a.state === 'open').length;
  return n || undefined;
}
