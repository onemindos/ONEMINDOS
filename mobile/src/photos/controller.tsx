// SPDX-License-Identifier: Apache-2.0
// Wires the engine to the app: finds Photos in the catalog, keeps settings and the ledger, runs a
// backup when the app opens (and every 15 minutes while it stays open), and registers the
// background task when backup is on. Always the phone's real library and the box's Photos service:
// the in-memory box (mockServer.ts) and the made-up library in media.ts are for tests only.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppState } from 'react-native';
import { useHubData } from '../data';
import { useSignedIn } from '../session';
import { setBackgroundBackup } from './background';
import { PhotoBackupContext, type BackgroundState, type PhotoBackupState } from './context';
import { discoverPhotos } from './discovery';
import { isRunning, runBackup, type Conditions, type Progress } from './engine';
import { DEFAULT_SETTINGS, type BackupSettings, type BackupStore, type Ledger } from './ledger';
import type { MediaAlbum, MediaPermission, MediaSource } from './media';
import { ExpoMedia, FileStore, PLATFORM, readConditions } from './native';
import { HttpPhotosApi } from './protocol';

const FOREGROUND_EVERY_MS = 15 * 60_000;

export function PhotoBackupProvider({ children }: { children: ReactNode }) {
  const { connection } = useSignedIn();
  const { apps } = useHubData();
  const parts = useMemo(() => ({ media: new ExpoMedia() as MediaSource, store: new FileStore() as BackupStore, conditions: readConditions }), []);

  const availability = useMemo(() => discoverPhotos(connection, apps), [connection, apps]);
  const api = useMemo(
    () => (availability.state === 'ok' ? new HttpPhotosApi({ baseUrl: availability.baseUrl, token: connection.token }) : undefined),
    [availability, connection.token],
  );

  const [settings, setSettings] = useState<BackupSettings>(DEFAULT_SETTINGS);
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [permission, setPermission] = useState<MediaPermission>();
  const [conditions, setConditions] = useState<Conditions>();
  const [background, setBackground] = useState<BackgroundState>('unknown');
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
        platform: PLATFORM,
        deviceName: PLATFORM === 'ios' ? 'iPhone' : 'Android phone',
        trigger: 'foreground',
        signal: signal.current,
        onProgress: setProgress,
      });
    } finally {
      setRunning(false);
      setProgress(undefined);
      await refresh();
    }
  }, [api, parts, refresh]);

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
    void setBackgroundBackup(settings.enabled && availability.state === 'ok').then(setBackground);
  }, [settings.enabled, availability.state]);

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
    runNow,
    stop,
    updateSettings,
    requestPermission,
    loadAlbums,
  };
  return <PhotoBackupContext.Provider value={value}>{children}</PhotoBackupContext.Provider>;
}
