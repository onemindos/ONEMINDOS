// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from 'react';
import { ActivityIndicator, Linking, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { ActionState, NodeStatus, PrincipalKind } from '../api/types';
import { useHubData } from '../data';
import { safeHttpUrl } from '../lib/scan';
import { formatAgo } from '../lib/time';
import { radius, space, useTheme, type Palette } from './theme';

export function Screen({ children, testID }: { children: ReactNode; testID?: string }) {
  const t = useTheme();
  const { refreshing, reload } = useHubData();
  return (
    <ScrollView
      testID={testID}
      style={{ backgroundColor: t.bg }}
      contentContainerStyle={{ padding: space.lg, gap: space.md, paddingBottom: space.xl * 2 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void reload()} tintColor={t.muted} />}
    >
      <DataAge />
      {children}
    </ScrollView>
  );
}

/** Says plainly when what is on screen is not current (failed refresh). */
export function DataAge() {
  const t = useTheme();
  const { error, fetchedAt } = useHubData();
  if (!error) return null;
  const age = fetchedAt ? formatAgo(Math.floor((Date.now() - fetchedAt) / 1000)) : undefined;
  return (
    <View style={[s.note, { backgroundColor: t.warnBg }]} accessibilityRole="alert">
      <Text style={{ color: t.warn, fontWeight: '600' }}>Could not refresh from the hub</Text>
      <Text style={{ color: t.warn }}>
        {error.message}
        {age ? `. Showing data from ${age}; it may be out of date.` : '.'}
      </Text>
    </View>
  );
}

export function Card({ children, testID }: { children: ReactNode; testID?: string }) {
  const t = useTheme();
  return (
    <View testID={testID} style={[s.card, { backgroundColor: t.card, borderColor: t.border }]}>
      {children}
    </View>
  );
}

export function H1({ children }: { children: ReactNode }) {
  const t = useTheme();
  return (
    <Text accessibilityRole="header" style={{ color: t.text, fontSize: 22, fontWeight: '700' }}>
      {children}
    </Text>
  );
}

export function H2({ children }: { children: ReactNode }) {
  const t = useTheme();
  return (
    <Text accessibilityRole="header" style={{ color: t.text, fontSize: 17, fontWeight: '600', marginTop: space.sm }}>
      {children}
    </Text>
  );
}

export function P({ children, muted, small }: { children: ReactNode; muted?: boolean; small?: boolean }) {
  const t = useTheme();
  return <Text style={{ color: muted ? t.muted : t.text, fontSize: small ? 13 : 15, lineHeight: small ? 18 : 21 }}>{children}</Text>;
}

export function Row({ label, value }: { label: string; value: ReactNode }) {
  const t = useTheme();
  return (
    <View style={s.row}>
      <Text style={{ color: t.muted, fontSize: 14 }}>{label}</Text>
      <Text style={{ color: t.text, fontSize: 14, flexShrink: 1, textAlign: 'right' }}>{value}</Text>
    </View>
  );
}

type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'neutral';
function tone(t: Palette, x: Tone) {
  switch (x) {
    case 'ok':
      return { fg: t.ok, bg: t.okBg };
    case 'warn':
      return { fg: t.warn, bg: t.warnBg };
    case 'bad':
      return { fg: t.bad, bg: t.badBg };
    case 'info':
      return { fg: t.info, bg: t.infoBg };
    default:
      return { fg: t.muted, bg: t.neutralBg };
  }
}

export function Badge({ label, tone: x = 'neutral' }: { label: string; tone?: Tone }) {
  const c = tone(useTheme(), x);
  return (
    <View style={[s.badge, { backgroundColor: c.bg }]}>
      <Text style={{ color: c.fg, fontSize: 12, fontWeight: '600' }}>{label}</Text>
    </View>
  );
}

export const STATUS_TONE: Record<NodeStatus, Tone> = { online: 'ok', stale: 'warn', offline: 'bad' };

export function StateBadge({ state }: { state: ActionState }) {
  const x: Tone =
    state === 'succeeded'
      ? 'ok'
      : state === 'awaiting_approval' || state === 'requested'
        ? 'info'
        : state === 'failed' || state === 'outcome_unknown'
          ? 'bad'
          : state === 'expired' || state === 'cancelled'
            ? 'neutral'
            : 'warn';
  return <Badge label={state.replace(/_/g, ' ')} tone={x} />;
}

/** person/agent is shown on every request: the whole point of approvals (§3). */
export function KindBadge({ kind }: { kind: PrincipalKind | undefined }) {
  return <Badge label={kind ?? 'unknown'} tone={kind === 'agent' ? 'warn' : 'neutral'} />;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  testID,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  testID?: string;
}) {
  const t = useTheme();
  const bg = variant === 'primary' ? t.accent : variant === 'danger' ? t.badBg : t.neutralBg;
  const fg = variant === 'primary' ? t.accentText : variant === 'danger' ? t.bad : t.text;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [s.btn, { backgroundColor: bg, opacity: disabled ? 0.45 : pressed ? 0.8 : 1 }]}
    >
      <Text style={{ color: fg, fontWeight: '600', fontSize: 15 }}>{label}</Text>
    </Pressable>
  );
}

export function LinkChip({ label, url }: { label: string; url: string | null | undefined }) {
  const t = useTheme();
  const safe = safeHttpUrl(url);
  if (!safe) return null;
  return (
    <Pressable accessibilityRole="link" onPress={() => void Linking.openURL(safe)} style={[s.badge, { backgroundColor: t.infoBg }]}>
      <Text style={{ color: t.info, fontSize: 13, fontWeight: '600' }}>{label} ↗</Text>
    </Pressable>
  );
}

export function Notice({ text, tone: x = 'info' }: { text: string; tone?: Tone }) {
  const c = tone(useTheme(), x);
  return (
    <View style={[s.note, { backgroundColor: c.bg }]} accessibilityLiveRegion="polite">
      <Text style={{ color: c.fg }}>{text}</Text>
    </View>
  );
}

export function Loading({ what }: { what: string }) {
  const t = useTheme();
  return (
    <View style={{ padding: space.xl, alignItems: 'center', gap: space.sm }}>
      <ActivityIndicator color={t.muted} />
      <Text style={{ color: t.muted }}>Loading {what}…</Text>
    </View>
  );
}

export const s = StyleSheet.create({
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radius, padding: space.lg, gap: space.sm },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: space.md },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, alignItems: 'center' },
  badge: { paddingHorizontal: space.sm, paddingVertical: 3, borderRadius: 999, alignSelf: 'flex-start' },
  btn: { paddingVertical: space.md, paddingHorizontal: space.lg, borderRadius: 10, alignItems: 'center', flexGrow: 1 },
  note: { padding: space.md, borderRadius: 10, gap: 2 },
});
