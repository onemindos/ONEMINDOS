// SPDX-License-Identifier: Apache-2.0
// The install secrets form on the phone (#528). It opens when the owner approves an install whose app
// needs values only a person can give (an API key, a password). The values are typed here, masked,
// sealed on this phone to the box's key and sent only inside the approval. They are never shown again,
// never logged, and dropped from memory once sealed or when the form closes.
import { useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import type { AppSecrets, SecretValues } from '../api/types';
import { KIND_LABEL, formProblems, generatedCount, ownerKeys, refOf } from '../lib/installSecrets';
import { Button, Card, H2, Notice, P } from '../ui/bits';
import { font, radiusControl, space, touchTarget, useTheme } from '../ui/theme';

export function InstallSecretsForm({
  appName,
  secrets,
  busy,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  appName: string;
  secrets: AppSecrets;
  busy: boolean;
  error?: string;
  submitLabel: string;
  onSubmit: (values: SecretValues) => void;
  onCancel: () => void;
}) {
  const t = useTheme();
  const [values, setValues] = useState<SecretValues>({});
  const [shown, setShown] = useState<Record<string, boolean>>({});
  const [checked, setChecked] = useState(false);
  // Typed values live only in this component's state: cleared on submit, gone when it unmounts.
  const keys = ownerKeys(secrets);
  const generated = generatedCount(secrets);
  const problems = checked ? formProblems(secrets, values) : {};

  const submit = () => {
    if (busy) return;
    if (Object.keys(formProblems(secrets, values)).length) {
      setChecked(true);
      return;
    }
    const typed = values;
    setValues({});
    setShown({});
    setChecked(false);
    onSubmit(typed);
  };

  return (
    <Card testID={`secrets-${secrets.app_id}`}>
      <H2>Secrets for {appName}</H2>
      <P muted small>
        Typed here, sealed on this phone to your hub, and sent with your approval. Nobody can read them on the way, and they are never shown again.
      </P>
      {keys.map(({ secret, key }) => {
        const ref = refOf(secret, key.key);
        const problem = problems[ref];
        const label = `${KIND_LABEL[key.kind]}: ${key.key}${key.required && !key.set ? ' (required)' : key.set ? ' (already set; leave empty to keep it)' : ' (optional)'}`;
        return (
          <View key={ref} style={{ gap: space.xs }}>
            <Text style={{ color: t.text, fontSize: font.sm, fontWeight: font.semibold }}>{label}</Text>
            {!!key.description && <P muted small>{key.description}</P>}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
              <TextInput
                testID={`secret-${ref}`}
                accessibilityLabel={label}
                value={values[secret]?.[key.key] ?? ''}
                onChangeText={(v) => setValues((cur) => ({ ...cur, [secret]: { ...cur[secret], [key.key]: v } }))}
                secureTextEntry={!shown[ref]}
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="off"
                importantForAutofill="no"
                spellCheck={false}
                editable={!busy}
                style={{
                  flex: 1, minHeight: touchTarget, borderWidth: 1, borderRadius: radiusControl, paddingHorizontal: space.md,
                  color: t.text, backgroundColor: t.card, borderColor: problem ? t.danger : t.border,
                }}
              />
              <Pressable testID={`show-${ref}`} accessibilityRole="button" accessibilityLabel={`${shown[ref] ? 'Hide' : 'Show'} ${key.key}`}
                onPress={() => setShown((cur) => ({ ...cur, [ref]: !cur[ref] }))}
                style={{ minHeight: touchTarget, minWidth: touchTarget, justifyContent: 'center', alignItems: 'center' }}>
                <Text style={{ color: t.accent, fontSize: font.sm, fontWeight: font.semibold }}>{shown[ref] ? 'Hide' : 'Show'}</Text>
              </Pressable>
            </View>
            {problem && <Text testID={`problem-${ref}`} accessibilityLiveRegion="polite" style={{ color: t.danger, fontSize: font.sm }}>{problem}</Text>}
          </View>
        );
      })}
      {generated > 0 && <P muted small>{generated === 1 ? 'One more key is' : `${generated} more keys are`} made by the box itself.</P>}
      {error && <Notice tone="bad" text={error} />}
      <View style={{ gap: space.sm }}>
        <Button testID={`secrets-submit-${secrets.app_id}`} label={busy ? 'Sealing…' : submitLabel} disabled={busy} onPress={submit} />
        <Button testID={`secrets-cancel-${secrets.app_id}`} label="Cancel" variant="secondary" disabled={busy} onPress={onCancel} />
      </View>
    </Card>
  );
}
