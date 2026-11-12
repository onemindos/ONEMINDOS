// SPDX-License-Identifier: Apache-2.0
// Home tokens: the generated wallpapers (our own CSS gradients; no image assets) and the
// glass surface strength. Source of truth for home.css; a test checks the CSS matches and
// that text stays >= 4.5:1 on every wallpaper colour and on glass over it, in both themes.

export const HOME_WALLPAPER_IDS = ['tide', 'dusk', 'ember', 'fog'] as const;
export type HomeWallpaperId = (typeof HOME_WALLPAPER_IDS)[number];

export interface WallpaperStops {
  base: string;
  a: string;
  b: string;
  c: string;
}

export const HOME_WALLPAPER_NAME: Record<HomeWallpaperId, string> = { tide: 'Tide', dusk: 'Dusk', ember: 'Ember', fog: 'Fog' };

export const homeWallpapers: Record<'light' | 'dark', Record<HomeWallpaperId, WallpaperStops>> = {
  light: {
    tide: { base: '#eef5f4', a: '#c9e6e1', b: '#d9e4f5', c: '#e4f1e6' },
    dusk: { base: '#f2f0f8', a: '#dcd5f3', b: '#f1dbe6', c: '#d6e3f4' },
    ember: { base: '#f8f3ec', a: '#f3dcc0', b: '#f2d6d0', c: '#eae6cf' },
    fog: { base: '#f1f3f4', a: '#dde3e6', b: '#e6e9e3', c: '#dfe2ea' },
  },
  dark: {
    tide: { base: '#0b1517', a: '#123a38', b: '#13243d', c: '#0f2a22' },
    dusk: { base: '#110f1b', a: '#2a2050', b: '#3a1b33', c: '#172747' },
    ember: { base: '#16110b', a: '#3d2a12', b: '#3b1a17', c: '#2a2a14' },
    fog: { base: '#0f1314', a: '#1d272b', b: '#222626', c: '#1b1f29' },
  },
};

/** Share of `surface` in a glass panel; the rest is the wallpaper seen through it. */
export const GLASS_ALPHA = 0.84;

/** CSS custom property name for one stop, e.g. `--omh-wall-tide-a`. */
export const wallVar = (id: HomeWallpaperId, stop: keyof WallpaperStops) => `--omh-wall-${id}-${stop}`;
