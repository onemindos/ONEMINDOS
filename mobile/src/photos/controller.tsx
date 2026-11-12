// SPDX-License-Identifier: Apache-2.0
// Wires the engine to the app: finds Photos in the catalog, keeps settings and the ledger, runs a
// backup when the app opens (and every 15 minutes while it stays open), and registers the
// background task when backup is on. The demo uses an in-memory box and a made-up library.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppState } from 'react-native';
import { useHubData } from '../data';
import { useSignedIn } from '../session';
import { setBackgroundBackup } from './background';
import { PhotoBackupContext, type BackgroundState, type PhotoBackupState } from './context';
import { discoverPhotos } from './discovery';
import { isRunning, runBackup, type Conditions, type Progress } from './engine';
import { DEFAULT_SETTINGS, MemoryStore, type BackupSettings, type BackupStore, type Ledger } from './ledger';
import { demoLibrary, type MediaAlbum, type MediaPermission, type MediaSource } from './media';
import { MockPhotosServer } from './mockServer';
import { ExpoMedia, FileStore, PLATFORM, readConditions } from './native';
import { HttpPhotosApi } from './protocol';

const FOREGROUND_EVERY_MS = 15 * 60_000;

// Demo singletons: the in-memory box and library live as long as the app process.
let demo: { server: MockPhotosServer; media: MediaSource; store: BackupStore; conditions: Conditions } | undefined;
function demoParts(token: string) {
  if (!demo) {
    const server = new MockPhotosServer({ token, latencyMs: 120 });
    server.coverageRatio = { backed_up: 0.75, verified: 0.5 };
    demo = { server, media: demoLibrary(), store: new MemoryStore(), conditions: { network: 'wifi', power: 'charging' } };
  }
  return demo;
}

/** Screenshot tour hooks (src/tour.ts); only ever set in demo mode. */
export const photoTour: { enable?: () => Promise<void>; network?: (n: Conditions['network']) => void } = {};

export function PhotoBackupProvider({ children }: { children: ReactNode }) {
  const { connection } = useSignedIn();
  const { apps } = useHubData();
  const isDemo = connection.mode === 'mock';
  const parts = useMemo(() => {
    if (connection.mode === 'mock') {
      const d = demoParts(connection.token);
      return { ...d, conditions: async () => d.conditions, origin: d.server.origin, fetchFn: d.server.fetch, chunk: 512 * 1024 };
    }
    return { media: new ExpoMedia() as MediaSource, store: new FileStore() as BackupStore, conditions: readConditions, origin: '', fetchFn: undefined, chunk: undefined };
  }, [connection]);

  const availability = useMemo(() => discoverPhotos(connection, apps, parts.origin), [connection, apps, parts.origin]);
  const api = useMemo(
    () => (availability.state === 'ok' ? new HttpPhotosApi({ baseUrl: availability.baseUrl, token: connection.token, fetchFn: parts.fetchFn }) : undefined),
    [availability, connection.token, parts.fetchFn],
  );

  const [settings, setSettings] = useState<BackupSettings>(DEFAULT_SETTINGS);
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [permission, setPermission] = useState<MediaPermission>();
  const [conditions, setConditions] = useState<Conditions>();
  const [background, setBackground] = useState<BackgroundState>(isDemo ? 'demo' : 'unknown');
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<Progress>();
  const [albums, setAlbums] = useState<MediaAlbum[]>();
  const signal = useRef({ aborted: false });
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  const refresh = useCallback(async () => {
    const [l, p, c] = await Promise.all([parts.store.loadLedger(), parts.media.permission(false).catch(() => undefined), parts.conditions()]);
    setLedger(l);
    setPermission(p);
    setConditions(c);
  }, [parts]);

  useEffect(() => {
    void parts.store.loadSettings().then(setSettings);
    void refresh();
  }, [parts, refresh]);

  const runNow = useCallback(async () => {
    if (!api || isRunning()) return;
    signal.current = { aborted: false };
    setRunning(true);
    try {
      await runBackup({
        api,
        media: parts.media,
        store: parts.store,
        settings: settingsRef.current,
        conditions: parts.conditions,
        platform: isDemo ? 'ios' : PLATFORM,
        deviceName: isDemo ? 'Demo phone' : PLATFORM === 'ios' ? 'iPhone' : 'Android phone',
        trigger: 'foreground',
        signal: signal.current,
        chunkSize: parts.chunk,
        onProgress: setProgress,
      });
    } finally {
      setRunning(false);
      setProgress(undefined);
      await refresh();
    }
  }, [api, parts, isDemo, refresh]);

  // Run on open, on return to the foreground, and every 15 minutes while open.
  useEffect(() => {
    if (!api || !settings.enabled) return;
    void runNow();
    const id = setInterval(() => void runNow(), FOREGROUND_EVERY_MS);
    const sub = AppState.addEventListener('change', (s) => {
      if (s === 'active') void runNow();
    });
    return () => {
      clearInterval(id);
      sub.remove();
    };
  }, [api, settings.enabled, runNow]);

  useEffect(() => {
    if (isDemo) return;
    void setBackgroundBackup(settings.enabled && availability.state === 'ok').then(setBackground);
  }, [isDemo, settings.enabled, availability.state]);

  const updateSettings = useCallback(
    async (patch: Partial<BackupSettings>) => {
      const next = { ...settingsRef.current, ...patch };
      settingsRef.current = next;
      setSettings(next);
      await parts.store.saveSettings(next);
      if (patch.enabled) setPermission(await parts.media.permission(true));
      await refresh();
    },
    [parts, refresh],
  );

  const requestPermission = useCallback(async () => setPermission(await parts.media.permission(true)), [parts]);
  const loadAlbums = useCallback(async () => setAlbums(await parts.media.albums()), [parts]);
  const stop = useCallback(() => {
    signal.current.aborted = true;
  }, []);

  useEffect(() => {
    if (!isDemo) return;
    photoTour.enable = () => updateSettings({ enabled: true });
    photoTour.network = (n) => {
      demoParts(connection.mode === 'mock' ? connection.token : '').conditions = { network: n, power: 'charging' };
      void refresh().then(() => (n === 'wifi' ? runNow() : undefined));
    };
  }, [isDemo, updateSettings, refresh, runNow, connection]);

  const value: PhotoBackupState = {
    availability,
    settings,
    ledger,
    permission,
    conditions,
    background,
    running,
    progress,
    albums,
    host: api?.host,
    demo: isDemo,
    runNow,
    stop,
    updateSettings,
    requestPermission,
    loadAlbums,
  };
  return <PhotoBackupContext.Provider value={value}>{children}</PhotoBackupContext.Provider>;
}
