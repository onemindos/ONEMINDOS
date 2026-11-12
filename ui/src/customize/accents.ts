// SPDX-License-Identifier: Apache-2.0
// Accent palettes: 8 curated presets and the automatic WCAG AA fix for a custom colour.
// An accent set is the four accent roles of the tokens (accent, accent-hover, accent-text,
// accent-soft) for one theme. Every set this module returns passes the same contrast rules
// as the shipped tokens (ui/src/tokens/tokens.test.ts):
//   accent >= 4.5:1 on bg, surface, surface-raised and accent-soft;
//   accent-text >= 4.5:1 on accent and on accent-hover.
import { dark, light } from '../tokens/tokens';
import { contrast, hexToOklch, mix, normalizeHex, withLightness } from './color';

export type ThemeName = 'light' | 'dark';

/** Curated presets. Violet, red, amber and green hues are left out on purpose: they are
 * reserved for the agent tone and the status tones (PRINCIPLES P3), so an accent never
 * reads as "an agent did this" or "this failed". */
export const ACCENT_IDS = ['teal', 'lagoon', 'ink', 'graphite', 'moss', 'copper', 'rose', 'orchid'] as const;
export type AccentId = (typeof ACCENT_IDS)[number];

export interface AccentPreset {
  id: AccentId;
  name: string;
  /** Seed colours per theme; deriveAccent() turns them into a full, tested set. */
  light: string;
  dark: string;
}

export const ACCENTS: Record<AccentId, AccentPreset> = {
  teal: { id: 'teal', name: 'Teal', light: '#1f6a66', dark: '#6db8b0' },
  lagoon: { id: 'lagoon', name: 'Lagoon', light: '#0b6283', dark: '#6cc0e0' },
  ink: { id: 'ink', name: 'Ink', light: '#34488f', dark: '#a6b6ec' },
  graphite: { id: 'graphite', name: 'Graphite', light: '#3f4b55', dark: '#bcc7cf' },
  moss: { id: 'moss', name: 'Moss', light: '#4b6420', dark: '#a9c977' },
  copper: { id: 'copper', name: 'Copper', light: '#94461c', dark: '#eba37a' },
  rose: { id: 'rose', name: 'Rose', light: '#a02c5a', dark: '#f29bbd' },
  orchid: { id: 'orchid', name: 'Orchid', light: '#8a3683', dark: '#e3a2dc' },
};

export interface AccentSet {
  accent: string;
  hover: string;
  text: string;
  soft: string;
}

export interface DerivedAccent {
  set: AccentSet;
  /** The colour the person asked for (normalised). */
  requested: string;
  /** True when lightness was changed to reach AA. */
  adjusted: boolean;
  /** Worst contrast of the accent against the surfaces it sits on. */
  ratio: number;
}

export const AA = 4.5;

const SURFACES: Record<ThemeName, string[]> = {
  light: [light.bg, light.surface, light['surface-raised']],
  dark: [dark.bg, dark.surface, dark['surface-raised']],
};
const TEXT_ON_ACCENT: Record<ThemeName, string> = { light: light['accent-text'], dark: dark['accent-text'] };
const SOFT_ALPHA: Record<ThemeName, number> = { light: 0.1, dark: 0.18 };

function build(accent: string, theme: ThemeName): AccentSet {
  const l = hexToOklch(accent).l;
  const hover = withLightness(accent, theme === 'light' ? l - 0.06 : Math.min(0.96, l + 0.07));
  const surface = theme === 'light' ? light.surface : dark.surface;
  return { accent, hover, text: TEXT_ON_ACCENT[theme], soft: mix(accent, surface, SOFT_ALPHA[theme]) };
}

/** The worst ratio among every pair the tokens test checks for accents. */
export function accentWorstRatio(set: AccentSet, theme: ThemeName): number {
  return Math.min(
    ...SURFACES[theme].map((s) => contrast(set.accent, s)),
    contrast(set.accent, set.soft),
    contrast(set.text, set.accent),
    contrast(set.text, set.hover),
  );
}

/**
 * Turn any colour into an accent set that passes AA in `theme`. Hue and chroma are kept; only
 * OKLCH lightness moves (darker on light surfaces, lighter on dark ones) in small steps until
 * every pair passes. A colour that cannot pass at any lightness falls back to the brand teal.
 */
export function deriveAccent(seed: string, theme: ThemeName): DerivedAccent {
  const requested = normalizeHex(seed) ?? ACCENTS.teal[theme];
  const start = hexToOklch(requested).l;
  const step = theme === 'light' ? -0.01 : 0.01;
  for (let i = 0; i <= 100; i++) {
    const l = start + step * i;
    if (l < 0.05 || l > 0.97) break;
    const candidate = i === 0 ? requested : withLightness(requested, l);
    const set = build(candidate, theme);
    const ratio = accentWorstRatio(set, theme);
    if (ratio >= AA) return { set, requested, adjusted: i > 0, ratio };
  }
  const fallback = build(ACCENTS.teal[theme], theme);
  return { set: fallback, requested, adjusted: true, ratio: accentWorstRatio(fallback, theme) };
}

/** Both themes for one preset. */
export function presetAccent(id: AccentId): Record<ThemeName, DerivedAccent> {
  const p = ACCENTS[id];
  return { light: deriveAccent(p.light, 'light'), dark: deriveAccent(p.dark, 'dark') };
}

/** Both themes for a custom colour: the dark set starts from the same hue, made light enough. */
export function customAccent(hex: string): Record<ThemeName, DerivedAccent> {
  return { light: deriveAccent(hex, 'light'), dark: deriveAccent(hex, 'dark') };
}

export function isAccentId(v: unknown): v is AccentId {
  return typeof v === 'string' && (ACCENT_IDS as readonly string[]).includes(v);
}
