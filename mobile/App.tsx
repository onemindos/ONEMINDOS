// SPDX-License-Identifier: Apache-2.0
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import {
  createNavigationContainerRef,
  DarkTheme,
  DefaultTheme,
  NavigationContainer,
  type LinkingOptions,
  type Theme as NavTheme,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { Notifications } from './src/device/notifications';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { HubDataProvider, useHubData } from './src/data';
import type { Alert } from './src/lib/alerts';
import { deviceInfo, forgetDevice, renewWithDevice } from './src/lib/device';
import { useThisPhone } from './src/lib/install';
import { disablePush, installField, loadPushRecord, parsePing, platformTransport } from './src/lib/push';
import type { RootParams, TabParams } from './src/nav';
import { setBadge, setupNotifications, showAlert } from './src/notify';
import { PhotoBackupProvider } from './src/photos/controller';
import { PhotoAlbumsScreen } from './src/photos/PhotoAlbumsScreen';
import { PhotoBackupScreen } from './src/photos/PhotoBackupScreen';
import { usePushPings } from './src/pushPings';
import { IncomingFiles } from './src/files/IncomingFiles';
import { ActivityScreen } from './src/screens/ActivityScreen';
import { AppDetailScreen } from './src/screens/AppDetailScreen';
import { AgentsScreen } from './src/screens/AgentsScreen';
import { PeopleScreen } from './src/screens/PeopleScreen';
import { AutomationScreen } from './src/screens/AutomationScreen';
import { BackupsScreen } from './src/screens/BackupsScreen';
import { FilesScreen } from './src/screens/FilesScreen';
import { MigrateScreen } from './src/screens/MigrateScreen';
import { AppsScreen } from './src/screens/AppsScreen';
import { ApprovalsScreen } from './src/screens/ApprovalsScreen';
import { ConnectScreen } from './src/screens/ConnectScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { InboxScreen } from './src/screens/InboxScreen';
import { MoreScreen, useMoreBadge } from './src/screens/MoreScreen';
import { NodesScreen } from './src/screens/NodesScreen';
import { DeviceInfoScreen, LiveUsageScreen, NetworkScreen, OsUpdatesScreen, SystemControlsScreen } from './src/screens/SystemScreens';
import { TipsScreen } from './src/screens/TipsScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { PermissionsScreen } from './src/screens/PermissionsScreen';
import { useUpdateNeeded } from './src/lib/protocol';
import { UpdateNeededScreen } from './src/screens/UpdateNeededScreen';
import { onForgetHub, SessionProvider, useSession, useSignedIn, type SessionDeps } from './src/session';
import { PrefsProvider } from './src/prefs';
import { TabIcon } from './src/ui/TabIcon';
import { useIsDark, useTheme } from './src/ui/theme';

const Tab = createBottomTabNavigator<TabParams>();
const Stack = createNativeStackNavigator<RootParams>();
const navRef = createNavigationContainerRef<RootParams>();


/** Sessions renew with this phone's device key when the box has registered it (lib/device). */
const SESSION_DEPS: SessionDeps = { renewWithDevice };

// Forgetting a hub also turns push off there and drops this phone's device key and link.
onForgetHub(async (api, hubUrl) => {
  await disablePush(api, platformTransport(), await loadPushRecord(hubUrl));
  await forgetDevice();
});

const linking: LinkingOptions<RootParams> = {
  prefixes: ['onemind://'],
  config: {
    initialRouteName: 'Tabs',
    screens: {
      Tabs: { screens: { Home: 'home', Approvals: 'approvals', Apps: 'apps', Me: { path: 'me', alias: ['more'] } } },
      Activity: 'activity',
      AppDetail: 'apps/:id',
      Tips: 'tips/:id?',
      Settings: 'settings',
      PhotoBackup: 'photos',
      PhotoAlbums: 'photos/albums',
      Inbox: 'inbox',
      Nodes: 'nodes',
      Backups: 'backups',
      OsUpdates: 'os-updates',
      SystemControls: 'system-controls',
      DeviceInfo: 'device-info',
      LiveUsage: 'live-usage',
      Network: 'network',
      Automation: 'automation',
      Files: 'files',
      Migrate: 'migrate',
      People: 'people',
      Agents: 'agents',
    },
  },
};

function Tabs() {
  const t = useTheme();
  const { pendingCount } = useHubData();
  const moreBadge = useMoreBadge();
  useEffect(() => {
    void setBadge(pendingCount);
  }, [pendingCount]);
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarActiveTintColor: t.accent,
        tabBarInactiveTintColor: t.muted,
        tabBarLabelStyle: { fontSize: 12 },
        tabBarItemStyle: { minHeight: 48, paddingVertical: 3 },
        tabBarStyle: { backgroundColor: t.card, borderTopColor: t.border },
        tabBarBadgeStyle: { backgroundColor: t.action, color: t.actionText, fontSize: 12 },
        headerStyle: { backgroundColor: t.card },
        headerTintColor: t.text,
        tabBarIcon: ({ color }) => <TabIcon name={route.name} color={color} />,
      })}
    >
      <Tab.Screen name="Home" component={HomeScreen} options={{ headerShown: false }} />
      <Tab.Screen name="Approvals" component={ApprovalsScreen} options={{ tabBarBadge: pendingCount || undefined }} />
      <Tab.Screen name="Apps" component={AppsScreen} />
      <Tab.Screen name="Me" component={MoreScreen} options={{ headerShown: false, tabBarBadge: moreBadge, tabBarButtonTestID: 'tab-me' }} />
    </Tab.Navigator>
  );
}

/** Where a notification tap goes. A ping (ids only) opens the Inbox; nothing is ever approved from a tap. */
function routeTo(data: Record<string, unknown> | undefined) {
  if (!navRef.isReady()) return;
  const route = data?.route;
  if (route === 'approvals') navRef.navigate('Tabs', { screen: 'Approvals' });
  else if (route === 'activity') navRef.navigate('Activity');
  else if (route === 'nodes') navRef.navigate('Nodes');
  else if (route === 'inbox' || parsePing(data)) navRef.navigate('Inbox');
}

/** Pings from the box while the app runs (mobile/docs/push.md §5). */
function PushPings() {
  const { api, connection, features } = useSignedIn();
  const { reload } = useHubData();
  // The same name and install id as this phone's sign-in and passkey, so a rotated endpoint stays on its device (#715).
  const phone = useThisPhone();
  const install = useMemo(() => installField(features, phone?.installId), [features, phone?.installId]);
  usePushPings({ api, hubUrl: connection.hubUrl, label: phone?.name ?? deviceInfo('').name, install, reload });
  return null;
}

function SignedIn() {
  const dark = useIsDark();
  const t = useTheme();
  const navTheme = useMemo<NavTheme>(() => {
    const base = dark ? DarkTheme : DefaultTheme;
    return { ...base, colors: { ...base.colors, primary: t.accent, background: t.bg, card: t.card, text: t.text, border: t.border, notification: t.danger } };
  }, [dark, t]);
  const onAlerts = useCallback((alerts: Alert[]) => {
    for (const a of alerts) void showAlert(a).catch(() => undefined);
  }, []);

  useEffect(() => {
    void setupNotifications().catch(() => false);
    const sub = Notifications.addNotificationResponseReceivedListener((r) => routeTo(r.notification.request.content.data));
    return () => sub.remove();
  }, []);

  return (
    <HubDataProvider onAlerts={onAlerts}>
      <PushPings />
      <IncomingFiles />
      <PrefsProvider>
      <PhotoBackupProvider>
        <NavigationContainer ref={navRef} linking={linking} theme={navTheme}>
          <Stack.Navigator screenOptions={{ headerBackTitle: 'Back', headerStyle: { backgroundColor: t.card }, headerTintColor: t.text }}>
            <Stack.Screen name="Tabs" component={Tabs} options={{ headerShown: false }} />
            <Stack.Screen name="Activity" component={ActivityScreen} />
            <Stack.Screen name="AppDetail" component={AppDetailScreen} options={{ title: 'App' }} />
            <Stack.Screen name="Tips" component={TipsScreen} />
            <Stack.Screen name="Settings" component={SettingsScreen} />
            <Stack.Screen name="Permissions" component={PermissionsScreen} />
            <Stack.Screen name="Inbox" component={InboxScreen} />
            <Stack.Screen name="Nodes" component={NodesScreen} />
            <Stack.Screen name="Backups" component={BackupsScreen} />
            <Stack.Screen name="OsUpdates" component={OsUpdatesScreen} options={{ title: 'OS updates' }} />
            <Stack.Screen name="SystemControls" component={SystemControlsScreen} options={{ title: 'System controls' }} />
            <Stack.Screen name="DeviceInfo" component={DeviceInfoScreen} options={{ title: 'About this box' }} />
            <Stack.Screen name="LiveUsage" component={LiveUsageScreen} options={{ title: 'Live usage' }} />
            <Stack.Screen name="Network" component={NetworkScreen} />
            <Stack.Screen name="Automation" component={AutomationScreen} />
            <Stack.Screen name="Files" component={FilesScreen} />
            <Stack.Screen name="Migrate" component={MigrateScreen} options={{ title: 'Migration' }} />
            <Stack.Screen name="People" component={PeopleScreen} />
            <Stack.Screen name="Agents" component={AgentsScreen} />
            <Stack.Screen name="PhotoBackup" component={PhotoBackupScreen} options={{ title: 'Photo backup' }} />
            <Stack.Screen name="PhotoAlbums" component={PhotoAlbumsScreen} options={{ title: 'Albums to back up' }} />
          </Stack.Navigator>
        </NavigationContainer>
      </PhotoBackupProvider>
      </PrefsProvider>
    </HubDataProvider>
  );
}

function Root() {
  const t = useTheme();
  const { ready, session } = useSession();
  const update = useUpdateNeeded();
  if (!ready)
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: t.bg }}>
        <ActivityIndicator color={t.muted} />
      </View>
    );
  if (update) return <UpdateNeededScreen state={update} />;
  // Keyed by the hub, so switching hubs starts with fresh state and no stale data (a renewed token keeps the screen).
  return session ? <SignedIn key={session.connection.hubUrl} /> : <ConnectScreen />;
}

/** The whole app. It always talks HTTP to the owner's hub; tests hand in a fake gateway through `deps`. */
export function AppRoot({ deps = SESSION_DEPS }: { deps?: SessionDeps }) {
  return (
    <SafeAreaProvider>
      <SessionProvider deps={deps}>
        <Root />
        <StatusBar style="auto" />
      </SessionProvider>
    </SafeAreaProvider>
  );
}

export default function App() {
  return <AppRoot />;
}
