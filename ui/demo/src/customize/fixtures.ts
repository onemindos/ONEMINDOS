// SPDX-License-Identifier: Apache-2.0
// Typed fixtures for the Appearance demo. Bodies follow the proposed §12 shape of
// GET /v1/me/preferences: {"appearance": AppearancePreferences, "updated_at": RFC 3339}.
import { DEFAULT_APPEARANCE, PreferencesError, type AppearancePreferences, type PreferencesStore, type StoredPreferences } from '../../../src';

/** The demo's frozen hub clock (same instant as the other demo fixtures). */
export const CZ_NOW = new Date('2026-11-12T15:00:00Z');

export interface PreferencesResponse {
  appearance: AppearancePreferences;
  updated_at: string;
}

export const syncedResponse: PreferencesResponse = {
  appearance: { ...DEFAULT_APPEARANCE, wallpaper: 'tide', accentSource: 'wallpaper', wallpaperDim: 0.2, wallpaperBlur: 0 },
  updated_at: '2026-11-12T14:58:00Z',
};

export const customResponse: PreferencesResponse = {
  appearance: {
    ...DEFAULT_APPEARANCE,
    wallpaper: 'dunes',
    accentSource: 'custom',
    accentCustom: '#ffb400',
    wallpaperBlur: 12,
    wallpaperDim: 0.1,
    density: 'compact',
    corners: 'round',
    fontScale: 1.125,
  },
  updated_at: '2026-11-11T09:12:00Z',
};

export const browserCopy: PreferencesResponse = {
  appearance: { ...DEFAULT_APPEARANCE, wallpaper: 'fjord', accentSource: 'preset', accentPreset: 'ink' },
  updated_at: '2026-11-12T11:40:00Z',
};

/** In-memory store for the demo; `fail` makes every call reject like an unreachable hub. */
export class DemoStore implements PreferencesStore {
  private doc: StoredPreferences | null;
  constructor(
    readonly kind: 'local' | 'hub',
    seed: PreferencesResponse | null,
    private readonly fail: PreferencesError | null = null,
  ) {
    this.doc = seed ? { prefs: seed.appearance, updatedAt: seed.updated_at } : null;
  }
  async load(): Promise<StoredPreferences> {
    if (this.fail) throw this.fail;
    return this.doc ?? { prefs: DEFAULT_APPEARANCE, updatedAt: null };
  }
  async save(prefs: AppearancePreferences): Promise<StoredPreferences> {
    if (this.fail) throw this.fail;
    this.doc = { prefs, updatedAt: new Date().toISOString() };
    return this.doc;
  }
  async loadWallpaperImage() {
    return null;
  }
  async saveWallpaperImage() {
    if (this.fail) throw this.fail;
  }
}

export const unreachable = new PreferencesError('network', 'The hub could not be reached.');
