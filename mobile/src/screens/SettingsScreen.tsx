// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState } from 'react';
import { useNavigation } from '@react-navigation/native';
import { View } from 'react-native';
import { useHubData } from '../data';
import { loadLink, type DeviceLink } from '../lib/device';
import { renameThisPhone, useThisPhone } from '../lib/install';
import { setupNotifications, showAlert } from '../notify';
import { allowNotifications } from '../device/notifications';
import { useSignedIn } from '../session';
import { Button, Card, H1, H2, Notice, P, Row, Screen, s } from '../ui/bits';
import { AppearanceSection } from './AppearanceSection';
import { BoxSettingsSection } from './BoxSettingsSection';
import { DeviceSection } from './DeviceSection';
import { IdentitySection } from './IdentitySection';
import { PushSection } from './PushSection';

const LIVE_LABEL: Record<string, string> = {
  open: 'live (event stream)',
  connecting: 'connecting to the event stream…',
  retrying: 'reconnecting; checking every 10 s meanwhile',
  unsupported: 'checking every 10 s (this hub has no event stream)',
  forbidden: 'checking every 10 s (your account has no live updates)',
  off: 'checking every 10 s',
  stopped: 'paused',
  unauthenticated: 'signed out',
};

export function SettingsScreen() {
  const nav = useNavigation();
  const { connection, label, remembered, disconnect, features } = useSignedIn();
  const { instance, live } = useHubData();
  const [notif, setNotif] = useState<boolean>();
  const [link, setLink] = useState<DeviceLink>();
  const [disconnecting, setDisconnecting] = useState(false);
  const [disconnectFailed, setDisconnectFailed] = useState(false);
  // One name and one install id for every credential this phone holds (sign-in, passkey, push), so My devices
  // shows it as one device (#715). `draft` is what is typed; an empty box keeps the stored name until typed.
  const phone = useThisPhone();
  const [draft, setDraft] = useState<string>();
  const name = draft ?? phone?.name ?? '';
  const onName = useCallback((n: string) => {
    setDraft(n);
    if (n.trim()) void renameThisPhone(n);
  }, []);
  const hubUrl = connection.hubUrl;

  useEffect(() => {
    void setupNotifications().then(setNotif).catch(() => setNotif(false));
    if (hubUrl) void loadLink(hubUrl).then(setLink);
  }, [hubUrl]);
  const onLink = useCallback((l: DeviceLink) => setLink(l), []);

  return (
    <Screen testID="settings">
      <H1>Settings</H1>
      <IdentitySection phone={phone} />
      <AppearanceSection />
      <BoxSettingsSection />
      <DeviceSection link={link} onLink={onLink} name={name} onName={onName}
        onPermissions={() => nav.navigate('Permissions' as never)} />
      <PushSection deviceApproved={link?.state === 'active'} phone={phone} />
      <H2>Notifications on this phone</H2>
      <Card>
        <Row label="Allowed" value={notif === undefined ? 'checking…' : notif ? 'yes' : 'no'} />
        <P muted small>
          While the app is open it shows what is new on your box: approvals, finished actions and machines going offline. When
          the app is closed, push (above) wakes it.
        </P>
        <View style={s.wrap}>
          {notif === false && <Button variant="secondary" label="Allow notifications"
            onPress={() => void allowNotifications().then(setNotif).catch(() => setNotif(false))} />}
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
        <Row label="Updates" value={LIVE_LABEL[live] ?? live} />
        <Row label="Hub API" value={instance?.api?.version ?? (features.source === 'openapi' ? 'v0 routes and some §12 routes' : 'v0')} />
        <Row label="Remembered" value={remembered ? 'yes, in the secure store' : 'no (secure store unavailable); sign in again next time'} />
      </Card>
      <View style={s.wrap}>
        <Button testID="disconnect" variant="danger" label={disconnecting ? 'Disconnecting…' : 'Disconnect'}
          disabled={disconnecting} onPress={() => {
            setDisconnecting(true);
            setDisconnectFailed(false);
            void disconnect().catch(() => {
              setDisconnectFailed(true);
              setDisconnecting(false);
            });
          }} />
      </View>
      {disconnectFailed && <Notice tone="bad" text="OneMind could not finish signing out. Try Disconnect again." />}
      <P muted small>
        Disconnect signs this phone out, turns push off and removes the address, sign-in and device key from this phone's secure
        store. The owner can also remove this phone on the box.
      </P>
    </Screen>
  );
}
