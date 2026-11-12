// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState } from 'react';
import { View } from 'react-native';
import { useHubData } from '../data';
import { deviceInfo, loadLink, type DeviceLink } from '../lib/device';
import { setupNotifications, showAlert } from '../notify';
import { useSignedIn } from '../session';
import { Button, Card, H1, H2, Notice, P, Row, Screen, s } from '../ui/bits';
import { DeviceSection } from './DeviceSection';
import { IdentitySection } from './IdentitySection';
import { PushSection } from './PushSection';

const LIVE_LABEL: Record<string, string> = {
  open: 'live (event stream)',
  connecting: 'connecting to the event stream…',
  retrying: 'reconnecting; checking every 10 s meanwhile',
  unsupported: 'checking every 10 s (this hub has no event stream)',
  off: 'checking every 10 s',
  stopped: 'paused',
  unauthenticated: 'signed out',
};

export function SettingsScreen() {
  const { connection, label, remembered, disconnect, features } = useSignedIn();
  const { instance, live } = useHubData();
  const [notif, setNotif] = useState<boolean>();
  const [link, setLink] = useState<DeviceLink>();
  const [name, setName] = useState(() => deviceInfo('').name);
  const hubUrl = connection.mode === 'live' ? connection.hubUrl : undefined;

  useEffect(() => {
    void setupNotifications().then(setNotif).catch(() => setNotif(false));
    if (hubUrl) void loadLink(hubUrl).then(setLink);
  }, [hubUrl]);
  const onLink = useCallback((l: DeviceLink) => setLink(l), []);

  return (
    <Screen testID="settings">
      <H1>Settings</H1>
      <IdentitySection deviceName={name} />
      <DeviceSection link={link} onLink={onLink} name={name} onName={setName} />
      <PushSection deviceApproved={link?.state === 'active'} deviceName={name} />
      <H2>Notifications on this phone</H2>
      <Card>
        <Row label="Allowed" value={notif === undefined ? 'checking…' : notif ? 'yes' : 'no'} />
        <P muted small>
          While the app is open it shows what is new on your box: approvals, finished actions and machines going offline. When
          the app is closed, push (above) wakes it.
        </P>
        <View style={s.wrap}>
          <Button
            variant="secondary"
            label="Send a test alert"
            disabled={!notif}
            onPress={() => void showAlert({ id: `test-${Date.now()}`, title: 'OneMind', body: 'Test alert from this phone.', route: 'activity' })}
          />
        </View>
      </Card>
      <H2>Connection</H2>
      <Card>
        <Row label="Hub" value={label} />
        <Row label="Instance" value={instance?.name ?? 'unknown'} />
        <Row label="Mode" value={connection.mode === 'mock' ? 'demo (made-up data)' : 'live'} />
        <Row label="Updates" value={LIVE_LABEL[live] ?? live} />
        <Row label="Hub API" value={instance?.api?.version ?? (features.source === 'openapi' ? 'v0 routes and some §12 routes' : 'v0')} />
        <Row label="Remembered" value={remembered ? 'yes, in the secure store' : 'no (secure store unavailable); sign in again next time'} />
      </Card>
      {connection.mode === 'mock' && <Notice text="You are in the demo. Disconnect to connect to a real hub." />}
      <View style={s.wrap}>
        <Button testID="disconnect" variant="danger" label="Disconnect" onPress={() => void disconnect()} />
      </View>
      <P muted small>
        Disconnect signs this phone out, turns push off and removes the address, sign-in and device key from this phone's secure
        store. The owner can also remove this phone on the box.
      </P>
    </Screen>
  );
}
