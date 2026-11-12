// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react';
import { useHubData } from '../data';
import { setupNotifications, showAlert } from '../notify';
import { useSignedIn } from '../session';
import { Button, Card, H1, H2, Notice, P, Row, Screen, s } from '../ui/bits';
import { View } from 'react-native';

export function SettingsScreen() {
  const { connection, label, principal, remembered, disconnect } = useSignedIn();
  const { instance } = useHubData();
  const [notif, setNotif] = useState<boolean>();
  useEffect(() => {
    void setupNotifications().then(setNotif).catch(() => setNotif(false));
  }, []);
  return (
    <Screen testID="settings">
      <H1>Settings</H1>
      <Card>
        <Row label="Hub" value={label} />
        <Row label="Instance" value={instance?.name ?? 'unknown'} />
        <Row label="Mode" value={connection.mode === 'mock' ? 'demo (made-up data)' : 'live'} />
        <Row label="Remembered" value={remembered ? 'yes, in the secure store' : 'no (secure store unavailable); sign in again next time'} />
        <Row label="You are" value={principal ? `${principal.kind} ${principal.id} (${principal.role})` : 'known to the hub only'} />
      </Card>
      <H2>Notifications</H2>
      <Card>
        <Row label="Allowed" value={notif === undefined ? 'checking…' : notif ? 'yes' : 'no'} />
        <P muted small>
          While the app is open it checks the hub every 10 seconds and alerts you about new approvals, finished actions and
          nodes going offline. Alerts while the app is closed need push: UnifiedPush through the ntfy app on Android, and a
          content-free Apple push relay on iPhone (decision D-005). Neither is built yet.
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
      {connection.mode === 'mock' && <Notice text="You are in the demo. Disconnect to connect to a real hub." />}
      <View style={s.wrap}>
        <Button testID="disconnect" variant="danger" label="Disconnect" onPress={() => void disconnect()} />
      </View>
      <P muted small>Disconnect removes the address and token from this phone's secure store.</P>
    </Screen>
  );
}
