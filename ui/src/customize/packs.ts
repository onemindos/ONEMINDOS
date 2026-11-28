// SPDX-License-Identifier: Apache-2.0
// Theme packs: the founder's picks (2026-11-21) are Atlas's packs plus Console's packs. A pack is
// only a bundle of the appearance fields that already exist (theme, accent, wallpaper, corners,
// transparency), so applying one never touches text size, density, motion or the command bar.
// Boot splash, terminal palette and lock screen are part of the studio proposals but need OS
// image work; they are not set here. Wallpapers are OneMind's own procedural ones, each pack on
// the one the final design names (Console's set). No pack sets a button colour: buttons stay
// signal red in every pack, and every pack keeps the highlight off red (teal, or a calm non-red hue):
// red only means act or needs you (founder answers, 2026-11-21).
import type { AppearancePreferences } from './preferences';

export interface ThemePack {
  id: string;
  name: string;
  source: 'Atlas' | 'Console';
  note: string;
  set: Pick<AppearancePreferences, 'theme' | 'accentPreset' | 'wallpaper' | 'corners' | 'transparency'>;
}

const base = { accentSource: 'preset' } as const;
export const PACK_BASE: Pick<AppearancePreferences, 'accentSource'> = base;

export const THEME_PACKS: readonly ThemePack[] = [
  { id: 'atlas-night', name: 'Atlas Night', source: 'Atlas', note: 'Dark, Contour wallpaper, teal highlights.', set: { theme: 'dark', accentPreset: 'teal', wallpaper: 'contour', corners: 'standard', transparency: 'system' } },
  { id: 'atlas-day', name: 'Atlas Day', source: 'Atlas', note: 'Light, the same map by day.', set: { theme: 'light', accentPreset: 'teal', wallpaper: 'contour', corners: 'standard', transparency: 'system' } },
  { id: 'night-watch', name: 'Night Watch', source: 'Atlas', note: 'Low glare for a dark room or a wall screen.', set: { theme: 'dark', accentPreset: 'teal', wallpaper: 'ember', corners: 'standard', transparency: 'off' } },
  { id: 'greenhouse', name: 'Greenhouse', source: 'Atlas', note: 'Light, moss green, readable in sunlight.', set: { theme: 'light', accentPreset: 'moss', wallpaper: 'mycelium', corners: 'round', transparency: 'system' } },
  { id: 'harbor', name: 'Harbor', source: 'Atlas', note: 'Dark blue with a warm copper accent.', set: { theme: 'dark', accentPreset: 'copper', wallpaper: 'signal', corners: 'standard', transparency: 'system' } },
  { id: 'onemind', name: 'OneMind', source: 'Console', note: 'Graphite, the Dawn wallpaper, red buttons.', set: { theme: 'dark', accentPreset: 'teal', wallpaper: 'dawn', corners: 'standard', transparency: 'system' } },
  { id: 'onemind-light', name: 'OneMind Light', source: 'Console', note: 'The same rules in daylight.', set: { theme: 'light', accentPreset: 'teal', wallpaper: 'dawn', corners: 'standard', transparency: 'system' } },
  { id: 'field', name: 'Field', source: 'Console', note: 'Night operations: solid surfaces, low glare.', set: { theme: 'dark', accentPreset: 'teal', wallpaper: 'ember', corners: 'sharp', transparency: 'off' } },
  { id: 'village', name: 'Village', source: 'Console', note: 'Warm and plain for shared screens.', set: { theme: 'light', accentPreset: 'copper', wallpaper: 'harvest', corners: 'round', transparency: 'system' } },
  { id: 'mono', name: 'Mono', source: 'Console', note: 'Highest contrast: no glass, the Lattice wallpaper.', set: { theme: 'dark', accentPreset: 'graphite', wallpaper: 'lattice', corners: 'sharp', transparency: 'off' } },
];

export function packIsActive(p: ThemePack, prefs: AppearancePreferences): boolean {
  return prefs.accentSource === 'preset' && (Object.keys(p.set) as (keyof ThemePack['set'])[]).every((k) => prefs[k] === p.set[k]);
}

export function packPatch(p: ThemePack): Partial<AppearancePreferences> {
  return { ...PACK_BASE, ...p.set };
}
