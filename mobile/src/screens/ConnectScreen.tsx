// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react';
import { Image, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, useColorScheme, View } from 'react-native';
import { ApiError } from '../api/types';
import { deviceInfo } from '../lib/device';
import { platformPasskeys } from '../lib/passkeys';
import { passkeySignIn, SignInError } from '../lib/signin';
import { PasskeyError, passkeyMessage, rpIdFor } from '../lib/webauthn';
import { JoinScanner } from '../pair/JoinScanner';
import { enrolWithCode, markUsed, PairError, readJoin, trustBox, type BoxPin } from '../pair/pair';
import { useSession } from '../session';
import type { LiveConnection } from '../storage';
import { Button, Card, H1, H2, Notice, P, s as base } from '../ui/bits';
import { font, radiusControl, space, useTheme } from '../ui/theme';

const MARK = { light: require('../../assets/brand/mark-color-256.png'), dark: require('../../assets/brand/mark-on-dark-256.png') };

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

function messageFor(e: unknown, hubUrl: string): string {
  if (e instanceof SignInError || e instanceof PairError) return e.message;
  if (e instanceof PasskeyError) return passkeyMessage(e, rpIdFor(hubUrl)).replace('approve on the dashboard', 'use an access token below').replace('Approve on the dashboard', 'Use an access token below');
  if (e instanceof ApiError) {
    if (e.code === 'unauthenticated') return 'The hub did not accept this token.';
    if (e.code === 'network') return `Could not reach the hub: ${e.message}`;
    return `The hub answered with an error: ${e.message}`;
  }
  return e instanceof Error ? e.message : String(e);
}

export function ConnectScreen() {
  const t = useTheme();
  const scheme = useColorScheme();
  const { connect, expiredHub } = useSession();
  const [hubUrl, setHubUrl] = useState(expiredHub ?? '');
  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [joinText, setJoinText] = useState('');
  const [scanning, setScanning] = useState(false);
  const [paired, setPaired] = useState<{ pin: BoxPin; code: string }>();
  const [enrol, setEnrol] = useState({ code: '', username: '', password: '' });

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(undefined);
    try {
      await fn();
    } catch (e) {
      setError(messageFor(e, hubUrl));
      if (e instanceof SignInError || e instanceof PasskeyError) setShowToken(true);
    } finally {
      setBusy(false);
    }
  }

  /** Join QR (scanned or typed): check it, find the box, pin its CA. Nothing else is sent before the pin. */
  const pairWith = (text: string) =>
    run(async () => {
      setScanning(false);
      setPaired(undefined);
      const q = await readJoin(text);
      const pin = await trustBox(q);
      setPaired({ pin, code: q.code });
      setHubUrl(pin.hubUrl);
      setJoinText('');
    });

  /** A sign-in after pairing spends the join code on this phone, so the same QR is never used twice. */
  async function finish(c: LiveConnection) {
    if (paired && c.hubUrl === paired.pin.hubUrl) await markUsed(paired.code);
    await connect(c);
  }

  const signInWithPasskey = () => run(async () => finish(await passkeySignIn(hubUrl, platformPasskeys(), { deviceName: deviceInfo('').name })));

  const joinWithEnrolment = () =>
    run(async () => {
      if (!paired) return;
      await finish(await enrolWithCode(paired.pin.hubUrl, enrol));
    });

  let expiredHost: string | undefined;
  try {
    expiredHost = expiredHub ? new URL(expiredHub).host : undefined;
  } catch {
    expiredHost = expiredHub;
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
        <Image
          source={scheme === 'dark' ? MARK.dark : MARK.light}
          style={{ width: 72, height: 72 }}
          accessibilityRole="image"
          accessibilityLabel="OneMind"
          testID="brand-mark"
        />
        <H1>Connect to your OneMind</H1>
        <P muted>Your phone talks only to your own hub. Nothing goes through a OneMind cloud.</P>
        {expiredHost && <Notice tone="warn" text={`Your sign-in to ${expiredHost} ended. Sign in again.`} />}
        {error && <Notice tone="bad" text={error} />}
        <Card testID="pair-card">
          <H2>Pair with your box</H2>
          {scanning ? (
            <JoinScanner onCode={(text) => void pairWith(text)} onCancel={() => setScanning(false)} />
          ) : paired ? (
            <View style={{ gap: space.sm }}>
              <Notice tone="ok" text={`This phone now trusts the box at ${paired.pin.hubUrl.replace(/^https:\/\//, '')}: its certificate matched the code and is pinned here.`} />
              <Text style={{ color: t.muted, fontSize: font.sm }}>Check that the box shows the same code</Text>
              <Text testID="join-short-code" selectable style={{ color: t.text, fontSize: font.lg, fontWeight: font.semibold, letterSpacing: 2 }}>
                {paired.code}
              </Text>
              <P muted small>Now sign in with your passkey below, or join with the enrolment code the owner made for you.</P>
              <TextInput
                testID="enrol-code"
                style={input}
                value={enrol.code}
                onChangeText={(code) => setEnrol((v) => ({ ...v, code }))}
                placeholder="Enrolment code"
                placeholderTextColor={t.subtle}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <TextInput
                testID="enrol-username"
                style={input}
                value={enrol.username}
                onChangeText={(username) => setEnrol((v) => ({ ...v, username }))}
                placeholder="Username (if the owner did not pick one)"
                placeholderTextColor={t.subtle}
                autoCapitalize="none"
                autoCorrect={false}
                textContentType="username"
              />
              <TextInput
                testID="enrol-password"
                style={input}
                value={enrol.password}
                onChangeText={(password) => setEnrol((v) => ({ ...v, password }))}
                placeholder="Choose a password"
                placeholderTextColor={t.subtle}
                secureTextEntry
                textContentType="newPassword"
              />
              <View style={base.wrap}>
                <Button
                  testID="enrol"
                  variant="secondary"
                  label={busy ? 'Joining…' : 'Join with the enrolment code'}
                  disabled={busy || !enrol.code.trim() || !enrol.password}
                  onPress={() => void joinWithEnrolment()}
                />
              </View>
            </View>
          ) : (
            <View style={{ gap: space.sm }}>
              <View style={base.wrap}>
                <Button testID="scan-join" label="Scan the box's code" disabled={busy} onPress={() => setScanning(true)} />
              </View>
              <TextInput
                testID="join-code"
                style={input}
                value={joinText}
                onChangeText={setJoinText}
                placeholder="Or type the code: onemind-join:v2?…"
                placeholderTextColor={t.subtle}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <View style={base.wrap}>
                <Button
                  testID="use-join-code"
                  variant="secondary"
                  label={busy ? 'Checking…' : 'Use this code'}
                  disabled={busy || !joinText.trim()}
                  onPress={() => void pairWith(joinText)}
                />
              </View>
              <P muted small>The code tells the phone where the box is and which certificate is really the box's, so there is no certificate warning.</P>
            </View>
          )}
        </Card>
        <Card>
          <Text style={{ color: t.muted, fontSize: 13 }}>Hub address</Text>
          <TextInput
            testID="hub-url"
            style={input}
            value={hubUrl}
            onChangeText={setHubUrl}
            placeholder="https://onemind.local:8443"
            placeholderTextColor={t.subtle}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            textContentType="URL"
          />
          {insecureHub(hubUrl) && (
            <Notice
              tone="warn"
              text="This address uses plain HTTP, so what you send can be read by anyone on the network path. Use the https:// address (port 8443), or reach the hub over a private VPN."
            />
          )}
          <View style={base.wrap}>
            <Button testID="passkey-sign-in" label={busy ? 'Signing in…' : 'Sign in with a passkey'} disabled={busy || !hubUrl.trim()} onPress={() => void signInWithPasskey()} />
          </View>
          <P muted small>Face ID, your fingerprint or your screen lock confirms it is you. No password, and nothing to copy from the box.</P>
          {!showToken ? (
            <Pressable testID="use-token" accessibilityRole="button" onPress={() => setShowToken(true)} style={{ minHeight: 44, justifyContent: 'center' }}>
              <Text style={{ color: t.accent, fontSize: font.sm, fontWeight: font.semibold }}>Use an access token instead</Text>
            </Pressable>
          ) : (
            <View style={{ gap: space.sm }}>
              <Text style={{ color: t.muted, fontSize: font.sm }}>Access token</Text>
              <TextInput
                testID="token"
                style={input}
                value={token}
                onChangeText={setToken}
                placeholder="Token from the hub's tokens file"
                placeholderTextColor={t.subtle}
                autoCapitalize="none"
                autoCorrect={false}
                secureTextEntry
                textContentType="password"
              />
              <View style={base.wrap}>
                <Button
                  testID="connect"
                  variant="secondary"
                  label={busy ? 'Connecting…' : 'Connect with the token'}
                  disabled={busy || !hubUrl.trim() || !token.trim()}
                  onPress={() => void run(() => connect({ mode: 'live', hubUrl, token }))}
                />
              </View>
              <P muted small>
                For hubs without passkey sign-in (v0). The address and token are kept in this phone's secure store (Keychain on
                iPhone, Keystore on Android).
              </P>
            </View>
          )}
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
  input: { borderWidth: 1, borderRadius: radiusControl, paddingHorizontal: space.md, paddingVertical: space.md, fontSize: font.md, minHeight: 44 },
});
