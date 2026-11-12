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
import * as Notifications from 'expo-notifications';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo } from 'react';
import { ActivityIndicator, Image, Text, useColorScheme, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { HubDataProvider, useHubData } from './src/data';
import type { Alert } from './src/lib/alerts';
import { deviceInfo, forgetDevice, renewWithDevice } from './src/lib/device';
import { disablePush, loadPushRecord, parsePing, platformTransport } from './src/lib/push';
import type { RootParams, TabParams } from './src/nav';
import { setBadge, setupNotifications, showAlert } from './src/notify';
import { photoTour, PhotoBackupProvider } from './src/photos/controller';
import { PhotoAlbumsScreen } from './src/photos/PhotoAlbumsScreen';
import { PhotoBackupScreen } from './src/photos/PhotoBackupScreen';
import { usePushPings } from './src/pushPings';
import { ActivityScreen } from './src/screens/ActivityScreen';
import { AppDetailScreen } from './src/screens/AppDetailScreen';
import { AppsScreen } from './src/screens/AppsScreen';
import { ApprovalsScreen } from './src/screens/ApprovalsScreen';
import { ConnectScreen } from './src/screens/ConnectScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { InboxScreen } from './src/screens/InboxScreen';
import { MoreScreen, useMoreBadge } from './src/screens/MoreScreen';
import { NodesScreen } from './src/screens/NodesScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { onForgetHub, SessionProvider, useSession, useSignedIn, type SessionDeps } from './src/session';
import { TOUR, TOUR_ROLE, TOUR_STEP_MS } from './src/tour';
import { font, useTheme } from './src/ui/theme';

const Tab = createBottomTabNavigator<TabParams>();
const Stack = createNativeStackNavigator<RootParams>();
const navRef = createNavigationContainerRef<RootParams>();

const MARK = { light: require('./assets/brand/mark-color-256.png'), dark: require('./assets/brand/mark-on-dark-256.png') };

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
    screens: {
      Tabs: { screens: { Home: 'home', Apps: 'apps', Approvals: 'approvals', Activity: 'activity', More: 'more' } },
      AppDetail: 'apps/:id',
      Settings: 'settings',
      PhotoBackup: 'photos',
      PhotoAlbums: 'photos/albums',
      Inbox: 'inbox',
      Nodes: 'nodes',
    },
  },
};

const ICON: Record<keyof TabParams, string> = { Home: '⌂', Apps: '▦', Approvals: '✓', Activity: '≡', More: '⋯' };

function HomeTitle() {
  const t = useTheme();
  const scheme = useColorScheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <Image source={scheme === 'dark' ? MARK.dark : MARK.light} style={{ width: 28, height: 28 }} accessibilityIgnoresInvertColors />
      <Text style={{ color: t.text, fontSize: font.lg, fontWeight: font.bold }}>OneMind</Text>
    </View>
  );
}

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
        tabBarStyle: { backgroundColor: t.card, borderTopColor: t.border },
        tabBarBadgeStyle: { backgroundColor: t.danger, color: t.dangerText },
        headerStyle: { backgroundColor: t.card },
        headerTintColor: t.text,
        tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 18 }}>{ICON[route.name]}</Text>,
      })}
    >
      <Tab.Screen name="Home" component={HomeScreen} options={{ title: 'Home', headerTitle: () => <HomeTitle /> }} />
      <Tab.Screen name="Apps" component={AppsScreen} />
      <Tab.Screen name="Approvals" component={ApprovalsScreen} options={{ tabBarBadge: pendingCount || undefined }} />
      <Tab.Screen name="Activity" component={ActivityScreen} />
      <Tab.Screen name="More" component={MoreScreen} options={{ tabBarBadge: moreBadge }} />
    </Tab.Navigator>
  );
}

/** Where a notification tap goes. A ping (ids only) opens the Inbox; nothing is ever approved from a tap. */
function routeTo(data: Record<string, unknown> | undefined) {
  if (!navRef.isReady()) return;
  const route = data?.route;
  if (route === 'approvals') navRef.navigate('Tabs', { screen: 'Approvals' });
  else if (route === 'activity') navRef.navigate('Tabs', { screen: 'Activity' });
  else if (route === 'nodes') navRef.navigate('Nodes');
  else if (route === 'inbox' || parsePing(data)) navRef.navigate('Inbox');
}

/** Pings from the box while the app runs (mobile/docs/push.md §5). */
function PushPings() {
  const { api, connection } = useSignedIn();
  const { reload } = useHubData();
  usePushPings({ api, hubUrl: connection.mode === 'live' ? connection.hubUrl : undefined, label: deviceInfo('').name, reload });
  return null;
}

function SignedIn() {
  const scheme = useColorScheme();
  const t = useTheme();
  const navTheme = useMemo<NavTheme>(() => {
    const base = scheme === 'dark' ? DarkTheme : DefaultTheme;
    return { ...base, colors: { ...base.colors, primary: t.accent, background: t.bg, card: t.card, text: t.text, border: t.border, notification: t.danger } };
  }, [scheme, t]);
  const onAlerts = useCallback((alerts: Alert[]) => {
    for (const a of alerts) void showAlert(a).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!TOUR_ROLE) return;
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      const step = TOUR[i];
      if (!step || !navRef.isReady()) return clearInterval(id);
      if ('tab' in step) navRef.navigate('Tabs', { screen: step.tab });
      else if ('screen' in step) navRef.navigate(step.screen);
      else if ('app' in step) navRef.navigate('AppDetail', { id: step.app });
      else if ('photos' in step) {
        if (step.photos === 'albums') navRef.navigate('PhotoAlbums');
        else navRef.navigate('PhotoBackup');
        if (step.photos === 'enable') void photoTour.enable?.();
        if (step.photos === 'cellular' || step.photos === 'wifi') photoTour.network?.(step.photos);
      } else navRef.navigate('Settings');
    }, TOUR_STEP_MS);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (TOUR_ROLE) return; // the permission prompt would cover the screenshots
    void setupNotifications().catch(() => false);
    const sub = Notifications.addNotificationResponseReceivedListener((r) => routeTo(r.notification.request.content.data));
    return () => sub.remove();
  }, []);

  return (
    <HubDataProvider onAlerts={onAlerts}>
      <PushPings />
      <PhotoBackupProvider>
        <NavigationContainer ref={navRef} linking={linking} theme={navTheme}>
          <Stack.Navigator screenOptions={{ headerBackTitle: 'Back', headerStyle: { backgroundColor: t.card }, headerTintColor: t.text }}>
            <Stack.Screen name="Tabs" component={Tabs} options={{ headerShown: false }} />
            <Stack.Screen name="AppDetail" component={AppDetailScreen} options={{ title: 'App' }} />
            <Stack.Screen name="Settings" component={SettingsScreen} />
            <Stack.Screen name="Inbox" component={InboxScreen} />
            <Stack.Screen name="Nodes" component={NodesScreen} />
            <Stack.Screen name="PhotoBackup" component={PhotoBackupScreen} options={{ title: 'Photo backup' }} />
            <Stack.Screen name="PhotoAlbums" component={PhotoAlbumsScreen} options={{ title: 'Albums to back up' }} />
          </Stack.Navigator>
        </NavigationContainer>
      </PhotoBackupProvider>
    </HubDataProvider>
  );
}

function Root() {
  const t = useTheme();
  const { ready, session, connect } = useSession();
  useEffect(() => {
    if (ready && !session && TOUR_ROLE) void connect({ mode: 'mock', token: `${TOUR_ROLE}-demo` });
  }, [ready, session, connect]);
  if (!ready)
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: t.bg }}>
        <ActivityIndicator color={t.muted} />
      </View>
    );
  // Keyed by the hub, so switching hubs starts with fresh state and no stale data (a renewed token keeps the screen).
  return session ? <SignedIn key={session.connection.mode === 'live' ? session.connection.hubUrl : session.connection.token} /> : <ConnectScreen />;
}

export default function App() {
  return (
    <SafeAreaProvider>
      <SessionProvider deps={SESSION_DEPS}>
        <Root />
        <StatusBar style="auto" />
      </SessionProvider>
    </SafeAreaProvider>
  );
}
