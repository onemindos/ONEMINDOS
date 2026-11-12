// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Linking, Platform, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { ApiError } from '../api/types';
import { useSession } from '../session';
import { Button, Card, H1, H2, Notice, P, s as base } from '../ui/bits';
import { space, useTheme } from '../ui/theme';

const DEMO_ROLES = [
  { token: 'owner-demo', label: 'Owner' },
  { token: 'adult-demo', label: 'Adult' },
  { token: 'agent-demo', label: 'Agent' },
] as const;

/** Plain HTTP to anything but this device sends the bearer token readable on the network. */
export function insecureHub(url: string): boolean {
  const v = url.trim().toLowerCase();
  if (!v.startsWith('http://')) return false;
  return !/^http:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/.test(v);
}

function messageFor(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === 'unauthenticated') return 'The hub did not accept this token.';
    if (e.code === 'network') return `Could not reach the hub: ${e.message}`;
    return `The hub answered with an error: ${e.message}`;
  }
  return e instanceof Error ? e.message : String(e);
}

export function ConnectScreen() {
  const t = useTheme();
  const { connect } = useSession();
  const [hubUrl, setHubUrl] = useState('');
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(undefined);
    try {
      await fn();
    } catch (e) {
      setError(messageFor(e));
    } finally {
      setBusy(false);
    }
  }

  // onemind://demo?as=owner opens the demo (mock data only; never a real hub or token).
  useEffect(() => {
    const open = (url: string | null | undefined) => {
      const m = url?.match(/^onemind:\/\/demo(?:\?as=(owner|adult|agent))?/);
      if (m) void run(() => connect({ mode: 'mock', token: `${m[1] ?? 'owner'}-demo` }));
    };
    void Linking.getInitialURL().then(open);
    const sub = Linking.addEventListener('url', (e) => open(e.url));
    return () => sub.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const input = [st.input, { color: t.text, borderColor: t.border, backgroundColor: t.card }];
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: t.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={{ padding: space.lg, paddingTop: space.xl * 2.5, gap: space.md }} keyboardShouldPersistTaps="handled">
        <H1>Connect to your OneMind</H1>
        <P muted>Your phone talks only to your own hub. Nothing goes through a OneMind cloud.</P>
        <Card>
          <Text style={{ color: t.muted, fontSize: 13 }}>Hub address</Text>
          <TextInput
            testID="hub-url"
            style={input}
            value={hubUrl}
            onChangeText={setHubUrl}
            placeholder="https://hub.example:8080"
            placeholderTextColor={t.muted}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            textContentType="URL"
          />
          <Text style={{ color: t.muted, fontSize: 13 }}>Access token</Text>
          <TextInput
            testID="token"
            style={input}
            value={token}
            onChangeText={setToken}
            placeholder="Token from the hub's tokens file"
            placeholderTextColor={t.muted}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
            textContentType="password"
          />
          {insecureHub(hubUrl) && (
            <Notice
              tone="warn"
              text="This address uses plain HTTP, so the token can be read by anyone on the network path. Use HTTPS, or reach the hub over a private VPN."
            />
          )}
          {error && <Notice tone="bad" text={error} />}
          <View style={base.wrap}>
            <Button
              testID="connect"
              label={busy ? 'Connecting…' : 'Connect'}
              disabled={busy || !hubUrl.trim() || !token.trim()}
              onPress={() => void run(() => connect({ mode: 'live', hubUrl, token }))}
            />
          </View>
          <P muted small>
            The address and token are kept in this phone's secure store (Keychain on iPhone, Keystore on Android). v0 uses a
            static token; passkey sign-in comes later.
          </P>
        </Card>
        <H2>Or try the demo</H2>
        <P muted small>Made-up nodes, apps and requests, so you can see every screen without a hub. Pick who you are:</P>
        <View style={base.wrap}>
          {DEMO_ROLES.map((r) => (
            <Button
              key={r.token}
              testID={`demo-${r.token}`}
              variant="secondary"
              label={r.label}
              disabled={busy}
              onPress={() => void run(() => connect({ mode: 'mock', token: r.token }))}
            />
          ))}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const st = StyleSheet.create({
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: space.md, paddingVertical: space.md, fontSize: 16 },
});
