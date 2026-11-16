// SPDX-License-Identifier: Apache-2.0
// UMB-P07: the theme the person chose, kept on the hub and shared with their desktop.
import { useState } from 'react';
import { View } from 'react-native';
import { usePrefs } from '../prefs';
import { Button, Card, H2, Notice, P, s } from '../ui/bits';

const CHOICES = [
  { id: 'system', label: 'Match phone' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
] as const;

export function AppearanceSection() {
  const { served, theme, setTheme } = usePrefs();
  const [error, setError] = useState<string>();
  if (!served) return null; // an older hub keeps no preferences
  return (
    <>
      <H2>Appearance</H2>
      <Card>
        <P muted small>Kept on your hub, so your phone and your desktop look the same.</P>
        <View style={s.wrap}>
          {CHOICES.map((c) => (
            <Button
              key={c.id}
              testID={`theme-${c.id}`}
              variant={theme === c.id ? 'primary' : 'secondary'}
              label={c.label}
              onPress={() => void setTheme(c.id).then(setError)}
            />
          ))}
        </View>
        {error ? <Notice tone="bad" text={error} /> : null}
      </Card>
    </>
  );
}
