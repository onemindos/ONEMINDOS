// SPDX-License-Identifier: Apache-2.0
// Appearance preferences: the per-person data model, validation, theme resolution and the
// translation into CSS custom properties and root attributes. Pure functions except
// applyPreferences(), which writes to a root element passed in (document by default).
// The stylesheet lives with the engine (not the barrel index.ts): package.json marks only
// *.css as side-effectful, so a CSS import in a re-export-only module is tree-shaken away.
import './customize.css';
import { customAccent, isAccentId, presetAccent, type AccentId, type DerivedAccent, type ThemeName } from './accents';
import { normalizeHex } from './color';
import { WALLPAPERS, isWallpaperChoice, minDim, type WallpaperChoice } from './wallpapers';

export type ThemeMode = 'system' | 'light' | 'dark' | 'schedule';
export type AccentSource = 'wallpaper' | 'preset' | 'custom';
export type Density = 'comfortable' | 'compact';
export type Corners = 'sharp' | 'standard' | 'round';
export type MotionPref = 'system' | 'reduce';
export type TransparencyPref = 'system' | 'on' | 'off';

export const FONT_SCALES = [0.9, 1, 1.125, 1.25] as const;
export type FontScale = (typeof FONT_SCALES)[number];

export const MAX_BLUR = 40;

/** Version 1 of the appearance document. Field names are the proposed API shape (§12). */
export interface AppearancePreferences {
  version: 1;
  theme: ThemeMode;
  /** Local times "HH:MM" for theme = schedule; dark from `darkFrom` until `lightFrom`. */
  schedule: { darkFrom: string; lightFrom: string };
  accentSource: AccentSource;
  accentPreset: AccentId;
  /** `#rrggbb` as the person picked it; the applied colour may be adjusted for contrast. */
  accentCustom: string;
  wallpaper: WallpaperChoice;
  /** Blur in px, 0..MAX_BLUR. */
  wallpaperBlur: number;
  /** Dim as chosen, 0..0.95. The applied dim is never below the contrast minimum. */
  wallpaperDim: number;
  /** Sampled colours of an uploaded wallpaper, for the contrast guard; empty if unknown. */
  customWallpaperColors: string[];
  density: Density;
  fontScale: FontScale;
  corners: Corners;
  motion: MotionPref;
  transparency: TransparencyPref;
}

export const DEFAULT_PREFERENCES: AppearancePreferences = {
  version: 1,
  theme: 'system',
  schedule: { darkFrom: '19:00', lightFrom: '07:00' },
  accentSource: 'wallpaper',
  accentPreset: 'teal',
  accentCustom: '#1f6a66',
  wallpaper: 'aurora',
  wallpaperBlur: 0,
  wallpaperDim: 0.2,
  customWallpaperColors: [],
  density: 'comfortable',
  fontScale: 1,
  corners: 'standard',
  motion: 'system',
  transparency: 'system',
};

const TIME = /^([01]\d|2[0-3]):([0-5]\d)$/;
const pick = <T extends string>(v: unknown, allowed: readonly T[], d: T): T => (allowed.includes(v as T) ? (v as T) : d);
const num = (v: unknown, lo: number, hi: number, d: number) => (typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : d);

/**
 * Accept anything (stored JSON, an API body) and return valid preferences. Unknown or invalid
 * fields fall back to the default for that field only, so one bad value never loses the rest.
 */
export function normalizePreferences(input: unknown): AppearancePreferences {
  const d = DEFAULT_PREFERENCES;
  const o = (input && typeof input === 'object' ? input : {}) as Record<string, unknown>;
  const s = (o.schedule && typeof o.schedule === 'object' ? o.schedule : {}) as Record<string, unknown>;
  const colors = Array.isArray(o.customWallpaperColors)
    ? o.customWallpaperColors.map((c) => (typeof c === 'string' ? normalizeHex(c) : null)).filter((c): c is string => !!c).slice(0, 8)
    : [];
  return {
    version: 1,
    theme: pick(o.theme, ['system', 'light', 'dark', 'schedule'], d.theme),
    schedule: {
      darkFrom: typeof s.darkFrom === 'string' && TIME.test(s.darkFrom) ? s.darkFrom : d.schedule.darkFrom,
      lightFrom: typeof s.lightFrom === 'string' && TIME.test(s.lightFrom) ? s.lightFrom : d.schedule.lightFrom,
    },
    accentSource: pick(o.accentSource, ['wallpaper', 'preset', 'custom'], d.accentSource),
    accentPreset: isAccentId(o.accentPreset) ? o.accentPreset : d.accentPreset,
    accentCustom: (typeof o.accentCustom === 'string' && normalizeHex(o.accentCustom)) || d.accentCustom,
    wallpaper: isWallpaperChoice(o.wallpaper) ? o.wallpaper : d.wallpaper,
    wallpaperBlur: Math.round(num(o.wallpaperBlur, 0, MAX_BLUR, d.wallpaperBlur)),
    wallpaperDim: Math.round(num(o.wallpaperDim, 0, 0.95, d.wallpaperDim) * 100) / 100,
    customWallpaperColors: colors,
    density: pick(o.density, ['comfortable', 'compact'], d.density),
    fontScale: (FONT_SCALES as readonly number[]).includes(o.fontScale as number) ? (o.fontScale as FontScale) : d.fontScale,
    corners: pick(o.corners, ['sharp', 'standard', 'round'], d.corners),
    motion: pick(o.motion, ['system', 'reduce'], d.motion),
    transparency: pick(o.transparency, ['system', 'on', 'off'], d.transparency),
  };
}

const minutes = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
};

/** For theme = schedule: is it dark at this local time? Handles windows that cross midnight. */
export function scheduledTheme(schedule: AppearancePreferences['schedule'], at: Date): ThemeName {
  const now = at.getHours() * 60 + at.getMinutes();
  const df = minutes(schedule.darkFrom);
  const lf = minutes(schedule.lightFrom);
  if (df === lf) return 'light';
  const inDark = df > lf ? now >= df || now < lf : now >= df && now < lf;
  return inDark ? 'dark' : 'light';
}

/** Milliseconds from `at` until the next scheduled switch (at least 1 s). */
export function msUntilNextSwitch(schedule: AppearancePreferences['schedule'], at: Date): number {
  const now = at.getHours() * 60 + at.getMinutes();
  const next = [minutes(schedule.darkFrom), minutes(schedule.lightFrom)].map((t) => (t - now + 1440) % 1440 || 1440);
  const mins = Math.min(...next);
  return Math.max(1000, mins * 60_000 - at.getSeconds() * 1000 - at.getMilliseconds());
}

/** The `data-theme` to set: a forced theme, or null to follow the system. */
export function resolveThemeAttr(p: AppearancePreferences, at: Date): ThemeName | null {
  if (p.theme === 'light' || p.theme === 'dark') return p.theme;
  if (p.theme === 'schedule') return scheduledTheme(p.schedule, at);
  return null;
}

/** Which accent preset (or custom colour) the preferences resolve to. */
export function accentSeed(p: AppearancePreferences): { kind: 'preset'; id: AccentId } | { kind: 'custom'; hex: string } {
  if (p.accentSource === 'custom') return { kind: 'custom', hex: p.accentCustom };
  if (p.accentSource === 'wallpaper' && p.wallpaper !== 'none' && p.wallpaper !== 'custom') return { kind: 'preset', id: WALLPAPERS[p.wallpaper].accent };
  return { kind: 'preset', id: p.accentSource === 'wallpaper' ? 'teal' : p.accentPreset };
}

export function resolveAccent(p: AppearancePreferences): Record<ThemeName, DerivedAccent> {
  const s = accentSeed(p);
  return s.kind === 'custom' ? customAccent(s.hex) : presetAccent(s.id);
}

/** Dim actually applied in `theme`: the person's choice, raised to the contrast minimum. */
export function effectiveDim(p: AppearancePreferences, theme: ThemeName, accent?: string): { dim: number; min: number; raised: boolean } {
  if (p.wallpaper === 'none') return { dim: 0, min: 0, raised: false };
  const stops = p.wallpaper === 'custom' ? (p.customWallpaperColors.length ? p.customWallpaperColors : null) : WALLPAPERS[p.wallpaper].colors[theme];
  const min = minDim(stops, theme, accent);
  return { dim: Math.max(min, p.wallpaperDim), min, raised: min > p.wallpaperDim };
}

const RADII: Record<Corners, Record<string, string> | null> = {
  sharp: { xs: '2px', sm: '3px', md: '4px', lg: '6px', xl: '8px' },
  standard: null,
  round: { xs: '6px', sm: '10px', md: '14px', lg: '20px', xl: '28px' },
};

function accentVars(a: DerivedAccent, dim: number, indent: string): string {
  return [
    `--om-color-accent: ${a.set.accent};`,
    `--om-color-accent-hover: ${a.set.hover};`,
    `--om-color-accent-text: ${a.set.text};`,
    `--om-color-accent-soft: ${a.set.soft};`,
    `--om-wallpaper-dim: ${dim};`,
  ]
    .map((l) => indent + l)
    .join('\n');
}

/**
 * The stylesheet for these preferences. It mirrors the theme selectors of tokens.css with one
 * extra `:root` so it wins regardless of load order, and only overrides tokens: components keep
 * reading the same `--om-*` names.
 */
export function customizeCss(p: AppearancePreferences): string {
  const acc = resolveAccent(p);
  const lightDim = effectiveDim(p, 'light', acc.light.set.accent).dim;
  const darkDim = effectiveDim(p, 'dark', acc.dark.set.accent).dim;
  const radius = RADII[p.corners];
  const radiusVars = radius ? Object.entries(radius).map(([k, v]) => `  --om-radius-${k}: ${v};`).join('\n') + '\n' : '';
  return (
    '/* Generated by @onemind/ui customize: per-person appearance. */\n' +
    `:root:root {\n${accentVars(acc.light, lightDim, '  ')}\n  --om-wallpaper-blur: ${p.wallpaperBlur}px;\n${radiusVars}}\n` +
    `@media (prefers-color-scheme: dark) {\n  :root:root:not([data-theme='light']) {\n${accentVars(acc.dark, darkDim, '    ')}\n  }\n}\n` +
    `:root:root[data-theme='dark'] {\n${accentVars(acc.dark, darkDim, '  ')}\n}\n`
  );
}

export const STYLE_ID = 'om-customize';

export interface ApplyEnv {
  root?: HTMLElement;
  now?: Date;
  /** Whether the system asks for reduced transparency (matchMedia); default false. */
  systemReducedTransparency?: boolean;
}

/** Write the preferences onto the root element and the customize stylesheet. */
export function applyPreferences(p: AppearancePreferences, env: ApplyEnv = {}): void {
  const root = env.root ?? document.documentElement;
  const doc = root.ownerDocument;
  const theme = resolveThemeAttr(p, env.now ?? new Date());
  if (theme) root.setAttribute('data-theme', theme);
  else root.removeAttribute('data-theme');
  root.setAttribute('data-om-density', p.density);
  root.setAttribute('data-om-corners', p.corners);
  root.setAttribute('data-om-motion', p.motion);
  root.setAttribute('data-om-wallpaper', p.wallpaper === 'none' ? 'none' : 'on');
  const glass = p.transparency === 'on' || (p.transparency === 'system' && !env.systemReducedTransparency);
  root.setAttribute('data-om-glass', glass && p.wallpaper !== 'none' ? 'on' : 'off');
  if (p.fontScale === 1) root.style.removeProperty('font-size');
  else root.style.setProperty('font-size', `${p.fontScale * 100}%`);
  let style = doc.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!style) {
    style = doc.createElement('style');
    style.id = STYLE_ID;
    doc.head.appendChild(style);
  }
  style.textContent = customizeCss(p);
}

/** Remove everything applyPreferences() wrote. */
export function clearPreferences(root: HTMLElement = document.documentElement): void {
  for (const a of ['data-om-density', 'data-om-corners', 'data-om-motion', 'data-om-wallpaper', 'data-om-glass']) root.removeAttribute(a);
  root.style.removeProperty('font-size');
  root.ownerDocument.getElementById(STYLE_ID)?.remove();
}
