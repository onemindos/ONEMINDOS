// SPDX-License-Identifier: Apache-2.0
// Settings → This phone: ask the owner to add this phone to the box (action `device.add`,
// docs/umbrel2/clients.md §4.4). The owner approves it like any other request.
// Settings → My devices (#715): every phone, browser and app signed in as you, from GET /v1/me/devices,
// with Lost this device, which revokes everything that device holds (sign-ins, passkeys, approver keys,
// push) in one step. The hub asks for a fresh passkey (biometrics on this phone) once passkeys are on,
// and refuses the device you are using and an owner's last passkey.
import { useEffect, useState } from 'react';
import { Text, TextInput, View } from 'react-native';
import { OP } from '../api/client';
import { ApiError, type MyDevice } from '../api/types';
import { pollDevice, requestDevice, type DeviceLink } from '../lib/device';
import { requestError } from '../lib/manage';
import { formatAgo, secondsSince } from '../lib/time';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H2, Loading, Notice, P, Row, s } from '../ui/bits';
import { font, radiusControl, space, useTheme } from '../ui/theme';

const POLL_MS = 5000;

function ThisPhone({
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
  const hubUrl = connection.hubUrl;
  const supported = features.has(OP.deviceRequest);

  // While the owner has not answered, look again every few seconds (the screen is open, so it is cheap).
  useEffect(() => {
    if (!link || link.state !== 'pending') return;
    const id = setInterval(() => {
      void pollDevice(api, link).then(onLink).catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(id);
  }, [api, link, onLink]);

  if (!supported)
    return (
      <>
        <H2>This phone</H2>
        <Card testID="device">
          <P muted small>This hub does not register phones yet (device registry, CLIENT-2). The phone works with your sign-in alone until then.</P>
        </Card>
      </>
    );

  async function ask() {
    setBusy(true);
    setErr(undefined);
    try {
      onLink(await requestDevice(api, hubUrl, name));
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

export function DeviceSection(props: {
  link: DeviceLink | undefined;
  onLink: (l: DeviceLink) => void;
  name: string;
  onName: (n: string) => void;
  onPermissions?: () => void;
}) {
  const { features } = useSignedIn();
  return (
    <>
      <ThisPhone {...props} />
      {props.onPermissions && <Button variant="secondary" label="Permissions" onPress={props.onPermissions} />}
      {features.has(OP.myDevices) && <MyDevicesList />}
    </>
  );
}

const KIND: Record<MyDevice['kind'], string> = { phone: 'Phone', browser: 'Browser', app: 'App', unknown: 'Device' };
const SOURCE: Record<string, string> = { sessions: 'sign-in', passkeys: 'passkey', approver_keys: 'approver key', push: 'push registration' };

/** What a device holds, in words: "2 sign-ins, 1 passkey, 1 push registration". */
export function holds(d: MyDevice): string {
  const n = new Map<string, number>();
  for (const c of d.credentials) n.set(c.source, (n.get(c.source) ?? 0) + 1);
  return [...n].map(([k, v]) => `${v} ${SOURCE[k] ?? k}${v === 1 ? '' : 's'}`).join(', ') || 'nothing';
}

function removeError(e: unknown): string {
  if (e instanceof ApiError && e.reason === 'current_device') return 'This is the phone you are using. Sign out here instead.';
  if (e instanceof ApiError && e.reason === 'last_owner')
    return 'This device holds the last owner passkey on the box. Add a passkey on another device first.';
  return requestError(e, 'removing this device').text;
}

export function MyDevicesList() {
  const t = useTheme();
  const { api, features } = useSignedIn();
  const load = useLoad(() => api.myDevices(), [api]);
  const [asking, setAsking] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'ok' | 'bad'; text: string }>();
  const canRemove = features.has(OP.myDeviceRemove);
  const now = Date.now();

  async function remove(d: MyDevice) {
    setBusy(true);
    setMsg(undefined);
    try {
      const r = await api.removeMyDevice(d.id);
      const total = Object.values(r.revoked).reduce((a, b) => a + b, 0);
      setMsg(
        r.removed
          ? { tone: 'ok', text: `${d.label} is removed: ${total} credential${total === 1 ? '' : 's'} revoked. It has to sign in again to use this box.` }
          : { tone: 'ok', text: `${d.label} was already removed. Nothing was left to revoke.` },
      );
      setAsking(undefined);
      await load.reload();
    } catch (e) {
      setMsg({ tone: 'bad', text: removeError(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <H2>My devices</H2>
      <Card testID="my-devices">
        {load.loading && !load.data ? (
          <Loading what="your devices" />
        ) : load.error && !load.data ? (
          <Notice tone="bad" text={load.forbidden ? 'Sign in with your passkey on this phone to see your devices.' : `Could not load your devices: ${load.error.message}`} />
        ) : !load.data?.devices.length ? (
          <P muted small>No devices are signed in as you.</P>
        ) : (
          load.data.devices.map((d) => (
            <View key={d.id} testID={`my-device-${d.id}`} style={{ gap: 4, paddingVertical: 6 }}>
              <View style={s.wrap}>
                <Text style={{ color: t.text, fontWeight: font.semibold }}>{d.label}</Text>
                <Badge label={KIND[d.kind]} />
                {d.current && <Badge label="In use here" tone="ok" />}
              </View>
              <Row label="Last seen" value={d.last_seen_at ? formatAgo(secondsSince(d.last_seen_at, now)) : 'unknown'} />
              <Row label="Holds" value={holds(d)} />
              {canRemove && !d.current && asking !== d.id && (
                <View style={s.wrap}>
                  <Button testID={`my-device-lost-${d.id}`} variant="secondary" label="Lost this device" disabled={busy} onPress={() => setAsking(d.id)} />
                </View>
              )}
              {asking === d.id && (
                <>
                  <Notice tone="warn" text={`Remove ${d.label}? Its sign-ins, passkeys, approver keys and push are revoked at once. It has to sign in again to come back.`} />
                  <View style={s.wrap}>
                    <Button testID={`my-device-confirm-${d.id}`} variant="danger" label={busy ? 'Removing…' : 'Remove it'} disabled={busy} onPress={() => void remove(d)} />
                    <Button variant="secondary" label="Cancel" disabled={busy} onPress={() => setAsking(undefined)} />
                  </View>
                </>
              )}
            </View>
          ))
        )}
        {msg && <Notice tone={msg.tone} text={msg.text} />}
      </Card>
    </>
  );
}
