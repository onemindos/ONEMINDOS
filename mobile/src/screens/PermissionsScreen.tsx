// SPDX-License-Identifier: Apache-2.0
import { useFocusEffect } from '@react-navigation/native';
import { useCallback, useState } from 'react';
import { AppState, Linking, ScrollView, View } from 'react-native';
import { backgroundPermission } from '../device/background';
import { cameraPermission } from '../device/camera';
import { photosPermission } from '../device/files';
import { locationPermission } from '../device/location';
import { microphonePermission } from '../device/mic';
import { notificationPermission } from '../device/notifications';
import { Button, Card, H1, H2, Notice, P, Row } from '../ui/bits';
import { Contour } from '../ui/Contour';
import { space } from '../ui/theme';

const capabilities: ReadonlyArray<{
  title: string;
  why: string;
  apps: string;
  status: () => Promise<string>;
  systemSetting?: boolean;
}> = [
  { title: 'Camera', why: 'Scan a join code when you connect to a box.', apps: 'Connect', status: cameraPermission, systemSetting: true },
  { title: 'Microphone', why: 'Capture sound when you start a recording.', apps: 'Recorder', status: microphonePermission, systemSetting: true },
  { title: 'Location', why: 'Find this phone or show weather near you when you ask.', apps: 'Find My Devices and Weather',
    status: () => locationPermission(), systemSetting: true },
  { title: 'Background location', why: 'Allow a feature you enable to get the phone’s location while OneMind is closed.',
    apps: 'Find My Devices', status: () => locationPermission(true), systemSetting: true },
  { title: 'Local storage', why: 'Keep app data on this phone so it works offline. Signing out removes it.',
    apps: 'OneMind Sync', status: async () => 'Private to OneMind' },
  { title: 'Files', why: 'The system picker gives OneMind access to the files you choose.', apps: 'Files',
    status: async () => 'Access per file' },
  { title: 'Photos and videos', why: 'Back up the photos and videos you select.', apps: 'Photo backup', status: photosPermission, systemSetting: true },
  { title: 'Notifications', why: 'Tell you when a request is waiting or something changes on your box.', apps: 'Inbox and Approvals',
    status: notificationPermission, systemSetting: true },
  { title: 'Background tasks', why: 'Continue queued transfers when the phone allows it.', apps: 'Files and Photo backup',
    status: backgroundPermission, systemSetting: true },
];

export function PermissionsScreen() {
  const [states, setStates] = useState<string[]>([]);
  const [settingsFailed, setSettingsFailed] = useState(false);

  useFocusEffect(useCallback(() => {
    let active = true;
    let checks = 0;
    const refresh = async () => {
      const current = ++checks;
      const results = await Promise.all(capabilities.map(async ({ status }) => {
        try {
          return await status();
        } catch {
          return 'Unavailable';
        }
      }));
      if (active && current === checks) setStates(results);
    };
    void refresh();
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') void refresh();
    });
    return () => {
      active = false;
      subscription.remove();
    };
  }, []));

  return (
    <View style={{ flex: 1 }}>
      <Contour />
      <ScrollView testID="permissions" contentContainerStyle={{ padding: space.lg, gap: space.md, paddingBottom: space.xl * 2 }}>
      <H1>Permissions</H1>
      <P>OneMind asks for access when you use a feature that needs it.</P>
      {settingsFailed && <Notice text="Open your phone’s Settings and choose OneMind to change access." />}
      {capabilities.map(({ title, why, apps, systemSetting }, index) => (
        <Card key={title}>
          <H2>{title}</H2>
          <P>{why}</P>
          <Row label="Used by" value={apps} />
          <Row label="State" value={states[index] ?? 'Checking…'} />
          {systemSetting && states[index] !== 'Not available' && <Button variant="secondary" label={`Open phone settings for ${title.toLowerCase()}`}
            onPress={() => {
              setSettingsFailed(false);
              void Linking.openSettings().catch(() => setSettingsFailed(true));
            }} />}
        </Card>
      ))}
      </ScrollView>
    </View>
  );
}
