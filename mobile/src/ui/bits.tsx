// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from 'react';
import { ActivityIndicator, Linking, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { ActionState, NodeStatus, PrincipalKind } from '../api/types';
import { useHubData } from '../data';
import { safeHttpUrl } from '../lib/scan';
import { formatAgo } from '../lib/time';
import { font, radius, radiusControl, space, touchTarget, useTheme, type Palette } from './theme';

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
    <View style={[s.note, { backgroundColor: t.warnBg, borderColor: t.warnBorder }]} accessibilityRole="alert">
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
    <Text accessibilityRole="header" style={{ color: t.text, fontSize: font.xxl, fontWeight: font.bold }}>
      {children}
    </Text>
  );
}

export function H2({ children }: { children: ReactNode }) {
  const t = useTheme();
  return (
    <Text accessibilityRole="header" style={{ color: t.text, fontSize: font.lg, fontWeight: font.semibold, marginTop: space.sm }}>
      {children}
    </Text>
  );
}

export function P({ children, muted, small }: { children: ReactNode; muted?: boolean; small?: boolean }) {
  const t = useTheme();
  return (
    <Text style={{ color: muted ? t.muted : t.text, fontSize: small ? font.sm : font.md, lineHeight: (small ? font.sm : font.md) * 1.5 }}>{children}</Text>
  );
}

export function Row({ label, value }: { label: string; value: ReactNode }) {
  const t = useTheme();
  return (
    <View style={s.row}>
      <Text style={{ color: t.muted, fontSize: font.sm }}>{label}</Text>
      <Text style={{ color: t.text, fontSize: font.sm, flexShrink: 1, textAlign: 'right' }}>{value}</Text>
    </View>
  );
}

/** The design system's status tones; `agent` marks anything an AI agent did or asked for. */
export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'neutral' | 'agent';
export function tone(t: Palette, x: Tone) {
  switch (x) {
    case 'ok':
      return { fg: t.ok, bg: t.okBg, border: t.okBorder };
    case 'warn':
      return { fg: t.warn, bg: t.warnBg, border: t.warnBorder };
    case 'bad':
      return { fg: t.bad, bg: t.badBg, border: t.badBorder };
    case 'info':
      return { fg: t.info, bg: t.infoBg, border: t.infoBorder };
    case 'agent':
      return { fg: t.agent, bg: t.agentBg, border: t.agentBorder };
    default:
      return { fg: t.neutral, bg: t.neutralBg, border: t.neutralBorder };
  }
}

export function Badge({ label, tone: x = 'neutral' }: { label: string; tone?: Tone }) {
  const c = tone(useTheme(), x);
  return (
    <View style={[s.badge, { backgroundColor: c.bg, borderColor: c.border }]}>
      <Text style={{ color: c.fg, fontSize: font.xs, fontWeight: font.semibold }}>{label}</Text>
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
  return <Badge label={kind ?? 'unknown'} tone={kind === 'agent' ? 'agent' : 'neutral'} />;
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
  // ui/src/styles/components.css: primary = accent, secondary = surface with a strong border, danger = danger.
  const bg = variant === 'primary' ? t.accent : variant === 'danger' ? t.danger : t.card;
  const fg = variant === 'primary' ? t.accentText : variant === 'danger' ? t.dangerText : t.text;
  const border = variant === 'secondary' ? t.borderStrong : bg;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [s.btn, { backgroundColor: bg, borderColor: border, opacity: disabled ? 0.55 : pressed ? 0.85 : 1 }]}
    >
      <Text style={{ color: fg, fontWeight: font.semibold, fontSize: font.sm }}>{label}</Text>
    </Pressable>
  );
}

export function LinkChip({ label, url }: { label: string; url: string | null | undefined }) {
  const t = useTheme();
  const safe = safeHttpUrl(url);
  if (!safe) return null;
  return (
    <Pressable accessibilityRole="link" onPress={() => void Linking.openURL(safe)} style={[s.badge, { backgroundColor: t.accentSoft, borderColor: t.accentSoft }]}>
      <Text style={{ color: t.accent, fontSize: font.sm, fontWeight: font.semibold }}>{label} ↗</Text>
    </Pressable>
  );
}

export function Notice({ text, tone: x = 'info' }: { text: string; tone?: Tone }) {
  const c = tone(useTheme(), x);
  return (
    <View style={[s.note, { backgroundColor: c.bg, borderColor: c.border }]} accessibilityLiveRegion="polite">
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
  card: { borderWidth: 1, borderRadius: radius, padding: space.lg, gap: space.sm },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: space.md },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, alignItems: 'center' },
  badge: { paddingHorizontal: space.sm, paddingVertical: 3, borderRadius: 999, borderWidth: 1, alignSelf: 'flex-start' },
  btn: {
    minHeight: touchTarget,
    justifyContent: 'center',
    paddingHorizontal: space.lg,
    borderRadius: radiusControl,
    borderWidth: 1,
    alignItems: 'center',
    flexGrow: 1,
  },
  note: { padding: space.md, borderRadius: radiusControl, borderWidth: 1, gap: 2 },
});
