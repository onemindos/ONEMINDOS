// SPDX-License-Identifier: Apache-2.0
// Settings → This phone: ask the owner to add this phone to the box (action `device.add`,
// docs/umbrel2/clients.md §4.4). The owner approves it like any other request.
import { useEffect, useState } from 'react';
import { Text, TextInput, View } from 'react-native';
import { OP } from '../api/client';
import { ApiError } from '../api/types';
import { pollDevice, requestDevice, type DeviceLink } from '../lib/device';
import { useSignedIn } from '../session';
import { Button, Card, H2, Notice, P, Row, s } from '../ui/bits';
import { font, radiusControl, space, useTheme } from '../ui/theme';

const POLL_MS = 5000;

export function DeviceSection({
  link,
  onLink,
  name,
  onName,
}: {
  link: DeviceLink | undefined;
  onLink: (l: DeviceLink) => void;
  name: string;
  onName: (n: string) => void;
}) {
  const t = useTheme();
  const { api, features, connection } = useSignedIn();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();
  const hubUrl = connection.mode === 'live' ? connection.hubUrl : undefined;
  const supported = features.has(OP.deviceRequest);

  // While the owner has not answered, look again every few seconds (the screen is open, so it is cheap).
  useEffect(() => {
    if (!link || link.state !== 'pending') return;
    const id = setInterval(() => {
      void pollDevice(api, link).then(onLink).catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(id);
  }, [api, link, onLink]);

  if (!hubUrl || !supported)
    return (
      <>
        <H2>This phone</H2>
        <Card testID="device">
          <P muted small>
            {hubUrl
              ? 'This hub does not register phones yet (device registry, CLIENT-2). The phone works with your sign-in alone until then.'
              : 'In the demo this phone is not registered with a box.'}
          </P>
        </Card>
      </>
    );

  async function ask() {
    setBusy(true);
    setErr(undefined);
    try {
      onLink(await requestDevice(api, hubUrl!, name));
    } catch (e) {
      setErr(e instanceof ApiError ? `The hub refused: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  const state = link?.state;
  return (
    <>
      <H2>This phone</H2>
      <Card testID="device">
        {!link || state === 'denied' || state === 'revoked' ? (
          <>
            <P small>
              Adding this phone to your box is a request, like everything else: the owner approves it on this phone, the
              dashboard or the CLI. An owner's first phone may be approved at once.
            </P>
            {state === 'denied' && <Notice tone="warn" text="The owner said no to the last request." />}
            {state === 'revoked' && <Notice tone="warn" text="This phone was removed from the box." />}
            <Text style={{ color: t.muted, fontSize: font.sm }}>Name shown to the owner</Text>
            <TextInput
              testID="device-name"
              value={name}
              onChangeText={onName}
              maxLength={64}
              style={{ borderWidth: 1, borderColor: t.borderStrong, borderRadius: radiusControl, padding: space.md, color: t.text, backgroundColor: t.card, minHeight: 44 }}
            />
            {err && <Notice tone="bad" text={err} />}
            <View style={s.wrap}>
              <Button testID="device-request" label={busy ? 'Asking…' : 'Ask the owner to add this phone'} disabled={busy || !name.trim()} onPress={() => void ask()} />
            </View>
          </>
        ) : state === 'pending' ? (
          <>
            <Notice text="Waiting for the owner. The request is in Approvals; this screen updates when they decide." />
            <Row label="Request" value={link.requestId} />
            <View style={s.wrap}>
              <Button variant="secondary" label="Check now" onPress={() => void pollDevice(api, link).then(onLink).catch(() => undefined)} />
            </View>
          </>
        ) : (
          <>
            <Row label="State" value="approved" />
            {link.deviceId && <Row label="Device" value={link.deviceId} />}
            <Row label="Key" value="software, kept in this phone's secure store" />
            <P muted small>The box ties this phone's sign-in to a key that never leaves it. Revoke it on the box if the phone is lost.</P>
          </>
        )}
      </Card>
    </>
  );
}
