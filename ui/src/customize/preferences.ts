// SPDX-License-Identifier: Apache-2.0
// Appearance preferences: the per-person data model, validation, theme resolution and the
// translation into CSS custom properties and root attributes. Pure functions except
// applyPreferences(), which writes to a root element passed in (document by default).
// The stylesheet lives with the engine (not the barrel index.ts): package.json marks only
// *.css as side-effectful, so a CSS import in a re-export-only module is tree-shaken away.
import './customize.css';
import { ACCENTS, DEFAULT_ACCENT, customAccent, isAccentId, presetAccent, type AccentId, type DerivedAccent, type ThemeName } from './accents';
import { hexToOklch, mix, normalizeHex } from './color';
import { dark, light } from '../tokens/tokens';
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
  /** The run bar ("Run a command or ask an agent", Alt R), off by default. */
  commandBar: boolean;
  /** Buttons keep the signal red (default). Off: buttons use the highlight colour. */
  buttonsRed: boolean;
  /** Screen ids in the person's dock order; empty = the shipped order. The dock reads this. */
  dockOrder: string[];
  /** Labels under dock tiles. */
  dockLabels: boolean;
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
  higherContrast: boolean;
  focusAlways: boolean;
  underlineLinks: boolean;
  transparency: TransparencyPref;
}

export const DEFAULT_PREFERENCES: AppearancePreferences = {
  version: 1,
  commandBar: false,
  buttonsRed: true,
  dockOrder: [],
  dockLabels: true,
  theme: 'system',
  schedule: { darkFrom: '19:00', lightFrom: '07:00' },
  // Atlas starts with teal highlights; personal accents can override that choice.
  accentSource: 'preset',
  accentPreset: DEFAULT_ACCENT,
  accentCustom: ACCENTS[DEFAULT_ACCENT].light,
  wallpaper: 'contour',
  wallpaperBlur: 0,
  wallpaperDim: 0.2,
  customWallpaperColors: [],
  density: 'comfortable',
  fontScale: 1,
  corners: 'standard',
  motion: 'system',
  higherContrast: false,
  focusAlways: false,
  underlineLinks: false,
  transparency: 'system',
};

const SAFE_ID = /^[a-z0-9][a-z0-9._-]{0,40}$/i;
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
    commandBar: o.commandBar === true,
    buttonsRed: o.buttonsRed !== false,
    dockOrder: Array.isArray(o.dockOrder)
      ? Array.from(new Set(o.dockOrder.filter((x): x is string => typeof x === 'string' && SAFE_ID.test(x)))).slice(0, 24)
      : [],
    dockLabels: o.dockLabels !== false,
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
    higherContrast: o.higherContrast === true,
    focusAlways: o.focusAlways === true,
    underlineLinks: o.underlineLinks === true,
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

/** The most colourful sampled colour of the person's photo; deriveAccent() darkens it until text passes AA. */
export function photoColour(colors: string[]): string {
  return colors.reduce((best, c) => (hexToOklch(c).c > hexToOklch(best).c ? c : best), colors[0]!);
}

/** Which accent preset (or custom colour) the preferences resolve to. */
export function accentSeed(p: AppearancePreferences): { kind: 'preset'; id: AccentId } | { kind: 'custom'; hex: string } {
  if (p.accentSource === 'custom') return { kind: 'custom', hex: p.accentCustom };
  if (p.accentSource === 'wallpaper' && p.wallpaper === 'custom' && p.customWallpaperColors.length) return { kind: 'custom', hex: photoColour(p.customWallpaperColors) };
  if (p.accentSource === 'wallpaper' && p.wallpaper !== 'none' && p.wallpaper !== 'custom') {
    // Red means act or needs you, so a red wallpaper never turns the highlight red (founder, 2026-11-21).
    const id = WALLPAPERS[p.wallpaper].accent;
    return { kind: 'preset', id: id === 'onemind' ? DEFAULT_ACCENT : id };
  }
  return { kind: 'preset', id: p.accentSource === 'wallpaper' ? DEFAULT_ACCENT : p.accentPreset };
}

export function resolveAccent(p: AppearancePreferences): Record<ThemeName, DerivedAccent> {
  const s = accentSeed(p);
  return s.kind === 'custom' ? customAccent(s.hex) : presetAccent(s.id);
}

/** Dim actually applied in `theme`: the person's choice, raised to the contrast minimum. */
export function effectiveDim(p: AppearancePreferences, theme: ThemeName, accent?: string): { dim: number; min: number; raised: boolean } {
  if (p.wallpaper === 'none') return { dim: 0, min: 0, raised: false };
  const stops = p.wallpaper === 'custom' ? (p.customWallpaperColors.length ? p.customWallpaperColors : null) : WALLPAPERS[p.wallpaper].colors[theme];
  const ink = theme === 'light' ? light.accent : dark.accent;
  const tinted = stops && accent ? stops.map((stop) => mix(accent, stop, WALLPAPER_TINT)) : stops;
  const min = Math.max(minDim(tinted, theme, ink), minDim(stops, theme, accent));
  return { dim: Math.max(min, p.wallpaperDim), min, raised: min > p.wallpaperDim };
}

const RADII: Record<Corners, Record<string, string> | null> = {
  sharp: { xs: '2px', sm: '3px', md: '4px', lg: '6px', xl: '8px' },
  standard: null,
  round: { xs: '6px', sm: '10px', md: '14px', lg: '20px', xl: '28px' },
};

// A personal accent tints the artwork. Selection, action and logo roles are fixed.
const WALLPAPER_TINT = 0.08;

/** The highlight (selection, focus, map selection) is the accent; buttons keep `--om-color-action`
 * (signal red) unless the person turned "Buttons stay signal red" off. The default teal is left
 * to the shipped tokens, so a box that never changed it carries no override. */
function accentVars(a: DerivedAccent, dim: number, indent: string, p: AppearancePreferences): string {
  const lines = [
    `--om-wallpaper-tint: ${a.set.accent};`,
    `--om-wallpaper-tint-opacity: ${WALLPAPER_TINT};`,
    `--om-wallpaper-dim: ${dim};`,
  ];
  if (!(p.accentSource === 'preset' && p.accentPreset === DEFAULT_ACCENT)) {
    lines.push(
      `--om-color-accent: ${a.set.accent};`,
      `--om-color-accent-hover: ${a.set.hover};`,
      `--om-color-accent-text: ${a.set.text};`,
      `--om-color-accent-soft: ${a.set.soft};`,
      `--om-color-focus: ${a.set.accent};`,
    );
  }
  if (!p.buttonsRed) {
    lines.push(`--om-color-action: ${a.set.accent};`, `--om-color-action-hover: ${a.set.hover};`, `--om-color-action-text: ${a.set.text};`);
  }
  return lines.map((line) => indent + line).join('\n');
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
    `:root:root {\n${accentVars(acc.light, lightDim, '  ', p)}\n  --om-wallpaper-blur: ${p.wallpaperBlur}px;\n${radiusVars}}\n` +
    `@media (prefers-color-scheme: dark) {\n  :root:root:not([data-theme='light']) {\n${accentVars(acc.dark, darkDim, '    ', p)}\n  }\n}\n` +
    `:root:root[data-theme='dark'] {\n${accentVars(acc.dark, darkDim, '  ', p)}\n}\n`
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
  root.toggleAttribute('data-om-dock-labels-off', !p.dockLabels);
  root.setAttribute('data-om-corners', p.corners);
  root.setAttribute('data-om-motion', p.motion);
  root.toggleAttribute('data-om-high-contrast', p.higherContrast);
  root.toggleAttribute('data-om-focus-always', p.focusAlways);
  root.toggleAttribute('data-om-underline-links', p.underlineLinks);
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
  for (const a of ['data-om-density', 'data-om-corners', 'data-om-motion', 'data-om-wallpaper', 'data-om-glass', 'data-om-high-contrast', 'data-om-focus-always', 'data-om-underline-links', 'data-om-dock-labels-off']) root.removeAttribute(a);
  root.style.removeProperty('font-size');
  root.ownerDocument.getElementById(STYLE_ID)?.remove();
}
