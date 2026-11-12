// SPDX-License-Identifier: Apache-2.0
// Settings → Appearance demo (#/appearance[/state]). States: live (this browser), synced, custom,
// stale (hub unreachable, local copy), empty (nothing saved), loading, error. Fixtures only:
// the demo never calls a gateway.
import { useEffect, useMemo } from 'react';
import {
  AppearanceSettings,
  CustomizeProvider,
  LocalPreferencesStore,
  PageHeader,
  PendingPreferencesStore,
  WallpaperLayer,
  clearPreferences,
  type PreferencesStore,
} from '../../../src';
import './appearance-demo.css';
import { CZ_NOW, DemoStore, browserCopy, customResponse, syncedResponse, unreachable, type PreferencesResponse } from './fixtures';

export const APPEARANCE_STATES = ['live', 'synced', 'custom', 'stale', 'empty', 'loading', 'error'] as const;
type State = (typeof APPEARANCE_STATES)[number];

/** ?theme=light|dark (screenshots) pins the fixture's theme so the shot matches. */
function withTheme(r: PreferencesResponse): PreferencesResponse {
  const t = new URLSearchParams(window.location.search).get('theme');
  return t === 'light' || t === 'dark' ? { ...r, appearance: { ...r.appearance, theme: t } } : r;
}

function stores(state: State): { store: PreferencesStore; cache?: PreferencesStore; clock: () => Date } {
  const frozen = () => CZ_NOW;
  switch (state) {
    case 'synced':
      return { store: new DemoStore('hub', withTheme(syncedResponse)), clock: frozen };
    case 'custom':
      return { store: new DemoStore('hub', withTheme(customResponse)), clock: frozen };
    case 'stale':
      return { store: new DemoStore('hub', null, unreachable), cache: new DemoStore('local', withTheme(browserCopy)), clock: frozen };
    case 'empty':
      return { store: new DemoStore('local', null), clock: frozen };
    case 'loading':
      return { store: new PendingPreferencesStore(), clock: frozen };
    case 'error':
      return { store: new DemoStore('hub', null, unreachable), clock: frozen };
    default:
      return { store: new LocalPreferencesStore(), clock: () => new Date() };
  }
}

export function AppearanceDemo({ arg }: { arg?: string }) {
  const state: State = (APPEARANCE_STATES as readonly string[]).includes(arg ?? '') ? (arg as State) : 'live';
  const s = useMemo(() => stores(state), [state]);
  // Appearance is applied for the whole page while this screen is open; leave the rest of the
  // demo as it was when navigating away (the dashboard mounts the provider at its root instead).
  useEffect(() => () => clearPreferences(), []);
  return (
    <CustomizeProvider key={state} store={s.store} cache={s.cache} now={s.clock}>
      <WallpaperLayer />
      <PageHeader title="Appearance" lede="Make OneMind yours: theme, accent, wallpaper and layout. Saved for you only; it changes nothing on the box, so it needs no approval." />
      <nav className="cz-demo-states" aria-label="Demo state">
        <span className="d-demo-flag">Demo state</span>
        {APPEARANCE_STATES.map((st) => (
          <a key={st} href={`#/appearance/${st}`} aria-current={st === state ? 'page' : undefined}>
            {st}
          </a>
        ))}
      </nav>
      <AppearanceSettings />
    </CustomizeProvider>
  );
}
