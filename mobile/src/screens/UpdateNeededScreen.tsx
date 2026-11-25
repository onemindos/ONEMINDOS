// SPDX-License-Identifier: Apache-2.0
import { Text, View } from 'react-native';
import type { UpdateNeeded } from '../lib/protocol';
import { font, space, useTheme } from '../ui/theme';

/** Shown instead of every screen when the hub no longer serves this app's protocol generation. */
export function UpdateNeededScreen({ state }: { state: UpdateNeeded }) {
  const t = useTheme();
  return (
    <View testID="update-needed" accessibilityRole="alert" style={{ flex: 1, justifyContent: 'center', padding: space.xl, gap: space.md, backgroundColor: t.bg }}>
      <Text accessibilityRole="header" style={{ color: t.text, fontSize: font.xl, fontWeight: font.semibold }}>Update needed</Text>
      <Text style={{ color: t.text }}>
        This version of the OneMind app speaks protocol {state.sent}. Your hub now serves {state.min} to {state.max}, so it
        stopped answering this app rather than risk showing wrong data.
      </Text>
      <Text style={{ color: t.muted }}>Update OneMind from the App Store or Play Store, then open it again. Your hub and its data are fine.</Text>
    </View>
  );
}
