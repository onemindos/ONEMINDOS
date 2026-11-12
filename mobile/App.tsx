// SPDX-License-Identifier: Apache-2.0
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import {
  createNavigationContainerRef,
  DarkTheme,
  DefaultTheme,
  NavigationContainer,
  type LinkingOptions,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import * as Notifications from 'expo-notifications';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect } from 'react';
import { ActivityIndicator, Pressable, Text, useColorScheme, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { HubDataProvider, useHubData } from './src/data';
import type { Alert } from './src/lib/alerts';
import type { RootParams, TabParams } from './src/nav';
import { setBadge, setupNotifications, showAlert } from './src/notify';
import { ActivityScreen } from './src/screens/ActivityScreen';
import { AppDetailScreen } from './src/screens/AppDetailScreen';
import { AppsScreen } from './src/screens/AppsScreen';
import { ApprovalsScreen } from './src/screens/ApprovalsScreen';
import { ConnectScreen } from './src/screens/ConnectScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { NodesScreen } from './src/screens/NodesScreen';
import { photoTour, PhotoBackupProvider } from './src/photos/controller';
import { PhotoAlbumsScreen } from './src/photos/PhotoAlbumsScreen';
import { PhotoBackupScreen } from './src/photos/PhotoBackupScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { SessionProvider, useSession } from './src/session';
import { TOUR, TOUR_ROLE, TOUR_STEP_MS } from './src/tour';
import { useTheme } from './src/ui/theme';

const Tab = createBottomTabNavigator<TabParams>();
const Stack = createNativeStackNavigator<RootParams>();
const navRef = createNavigationContainerRef<RootParams>();

const linking: LinkingOptions<RootParams> = {
  prefixes: ['onemind://'],
  config: {
    screens: {
      Tabs: { screens: { Home: 'home', Nodes: 'nodes', Apps: 'apps', Approvals: 'approvals', Activity: 'activity' } },
      AppDetail: 'apps/:id',
      Settings: 'settings',
      PhotoBackup: 'photos',
      PhotoAlbums: 'photos/albums',
    },
  },
};

const ICON: Record<keyof TabParams, string> = { Home: '⌂', Nodes: '◎', Apps: '▦', Approvals: '✓', Activity: '≡' };

function Tabs() {
  const t = useTheme();
  const { pendingCount } = useHubData();
  useEffect(() => {
    void setBadge(pendingCount);
  }, [pendingCount]);
  return (
    <Tab.Navigator
      screenOptions={({ route, navigation }) => ({
        tabBarActiveTintColor: t.accent,
        tabBarInactiveTintColor: t.muted,
        tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 18 }}>{ICON[route.name]}</Text>,
        headerRight: () => (
          <Pressable accessibilityRole="button" accessibilityLabel="Settings" onPress={() => navigation.getParent()?.navigate('Settings')} style={{ paddingHorizontal: 16 }}>
            <Text style={{ color: t.accent, fontSize: 15 }}>Settings</Text>
          </Pressable>
        ),
      })}
    >
      <Tab.Screen name="Home" component={HomeScreen} options={{ title: 'OneMind' }} />
      <Tab.Screen name="Nodes" component={NodesScreen} />
      <Tab.Screen name="Apps" component={AppsScreen} />
      <Tab.Screen name="Approvals" component={ApprovalsScreen} options={{ tabBarBadge: pendingCount || undefined }} />
      <Tab.Screen name="Activity" component={ActivityScreen} />
    </Tab.Navigator>
  );
}

function routeTo(route: unknown) {
  if (!navRef.isReady()) return;
  const screen = route === 'approvals' ? 'Approvals' : route === 'nodes' ? 'Nodes' : route === 'activity' ? 'Activity' : undefined;
  if (screen) navRef.navigate('Tabs', { screen });
}

function SignedIn() {
  const scheme = useColorScheme();
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
      else if ('app' in step) navRef.navigate('AppDetail', { id: step.app });
      else if ('photos' in step) {
        if (step.photos === 'albums') navRef.navigate('PhotoAlbums');
        else navRef.navigate('PhotoBackup');
        if (step.photos === 'enable') void photoTour.enable?.();
        if (step.photos === 'cellular' || step.photos === 'wifi') photoTour.network?.(step.photos);
      }
      else navRef.navigate('Settings');
    }, TOUR_STEP_MS);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (TOUR_ROLE) return; // the permission prompt would cover the screenshots
    void setupNotifications().catch(() => false);
    const sub = Notifications.addNotificationResponseReceivedListener((r) => routeTo(r.notification.request.content.data?.route));
    return () => sub.remove();
  }, []);

  return (
    <HubDataProvider onAlerts={onAlerts}>
      <PhotoBackupProvider>
      <NavigationContainer ref={navRef} linking={linking} theme={scheme === 'dark' ? DarkTheme : DefaultTheme}>
        <Stack.Navigator screenOptions={{ headerBackTitle: "Back" }}>
          <Stack.Screen name="Tabs" component={Tabs} options={{ headerShown: false }} />
          <Stack.Screen name="AppDetail" component={AppDetailScreen} options={{ title: 'App' }} />
          <Stack.Screen name="Settings" component={SettingsScreen} />
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
  // Keyed by the connection, so switching hubs starts with fresh state and no stale data.
  return session ? <SignedIn key={JSON.stringify(session.connection.mode === 'live' ? session.connection.hubUrl : session.connection.token)} /> : <ConnectScreen />;
}

export default function App() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <Root />
        <StatusBar style="auto" />
      </SessionProvider>
    </SafeAreaProvider>
  );
}
