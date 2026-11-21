// SPDX-License-Identifier: Apache-2.0
// OneMind design tokens: the single source of truth (docs/design/TOKENS.md).
// `npm run tokens` writes src/tokens/tokens.css from this file; a unit test fails when they drift.
// Mobile (React Native) reads the same values from dist/tokens.json.
// Its only import is the generated brand file (brand/brand.json via scripts/brand-sync.py), with
// an explicit .ts extension so Node can run the generator on it directly.
import { brand } from './brand.generated.ts';

/** Raw colour ramps. Components never use these; they use the semantic roles below. */
export const palette = {
  neutral: {
    0: '#ffffff',
    25: '#f7f9f9',
    50: '#f0f3f3',
    100: '#e3e8e9',
    200: '#cdd5d7',
    300: '#aab5b8',
    400: '#808d91',
    500: '#5e6b70',
    600: '#475459',
    700: '#343f44',
    800: '#222b2f',
    850: '#1a2226',
    900: '#131a1d',
    950: '#0c1214',
  },
  teal: { 50: '#e8f4f3', 100: '#cce8e5', 200: '#9fd2cc', 300: '#6db8b0', 500: '#237d77', 600: '#1f6a66', 700: '#1b5653', 900: '#113432' },
  green: { 50: '#e7f6ec', 100: '#c9ecd4', 300: '#7ad69c', 600: '#1d7a43', 700: '#166236' },
  amber: { 50: '#fdf4dc', 100: '#f6e2a6', 300: '#f2c661', 600: '#8a5a00', 700: '#6b4500' },
  red: { 50: '#fdeceb', 100: '#f9d1ce', 300: '#ff9087', 600: '#b42318', 700: '#8f1c13' },
  blue: { 50: '#e8effd', 100: '#cfdcfb', 300: '#9bb5ff', 400: '#6d93f0', 600: '#2f5bea', 700: '#2447b8' },
  violet: { 50: '#efecfc', 100: '#ddd6f8', 300: '#b9a9ff', 600: '#5b45c4', 700: '#47359c' },
} as const;


/** Semantic colour roles. Every role exists in both themes. */
export type ColorRole =
  | 'bg'
  | 'surface'
  | 'surface-sunken'
  | 'surface-raised'
  | 'border'
  | 'border-strong'
  | 'control-border'
  | 'text'
  | 'text-muted'
  | 'text-subtle'
  | 'accent'
  | 'accent-hover'
  | 'accent-text'
  | 'accent-soft'
  | 'logo-brain'
  | 'logo-circuit'
  | 'focus'
  | 'danger'
  | 'danger-hover'
  | 'danger-text'
  | 'overlay'
  | `${Tone}-fg`
  | `${Tone}-bg`
  | `${Tone}-border`;

/** Status tones. `agent` marks anything an AI agent did or asked for. */
export const TONES = ['ok', 'warn', 'bad', 'info', 'neutral', 'agent'] as const;
export type Tone = (typeof TONES)[number];

export type Theme = Record<ColorRole, string>;

export const light: Theme = {
  // Direction A, "Gallery": cool slate greys (OKLCH hue ~250, chroma < 0.01). The accent is ink.
  bg: '#f4f5f7',
  surface: '#ffffff',
  'surface-sunken': '#eceef1',
  'surface-raised': '#ffffff',
  border: '#dfe2e7',
  'border-strong': '#c4c9d1',
  'control-border': '#858c97',
  text: '#14171c',
  'text-muted': '#4a515c',
  'text-subtle': '#5f6772',
  accent: '#1d2128',
  'accent-hover': '#353b45',
  'accent-text': '#ffffff',
  'accent-soft': '#e6e8ec',
  // The OneMind red lives in the logo only (brand, unchanged).
  'logo-brain': brand.logo.light.brain,
  'logo-circuit': brand.logo.light.circuit,
  focus: '#2563c9',
  danger: '#b3261e',
  'danger-hover': '#8c1d17',
  'danger-text': '#ffffff',
  overlay: 'rgba(16, 19, 24, 0.45)',
  'ok-fg': '#17603a',
  'ok-bg': '#e6f4ec',
  'ok-border': '#c4e5d1',
  'warn-fg': '#6e4a00',
  'warn-bg': '#fbf1d9',
  'warn-border': '#efd9a0',
  'bad-fg': '#9e1c1c',
  'bad-bg': '#fcebea',
  'bad-border': '#f3cbc8',
  'info-fg': '#1f4f9e',
  'info-bg': '#e7eefa',
  'info-border': '#c9d8f2',
  'neutral-fg': '#4a515c',
  'neutral-bg': '#eceef1',
  'neutral-border': '#d6dae0',
  'agent-fg': '#4b3a99',
  'agent-bg': '#eeebfa',
  'agent-border': '#d9d2f3',
};

export const dark: Theme = {
  bg: '#101216',
  surface: '#171a1f',
  'surface-sunken': '#0c0e11',
  'surface-raised': '#1e2228',
  border: '#262a31',
  'border-strong': '#3a404a',
  'control-border': '#6b7380',
  text: '#eceef1',
  'text-muted': '#a8afba',
  'text-subtle': '#8d95a1',
  accent: '#eceef1',
  // Does not brighten further than the resting colour: no glare at night.
  'accent-hover': '#d6d9df',
  'accent-text': '#14171c',
  'accent-soft': '#2a2f37',
  'logo-brain': brand.logo.dark.brain,
  'logo-circuit': brand.logo.dark.circuit,
  focus: '#8fb4ff',
  danger: '#ff8a80',
  'danger-hover': '#ffaba3',
  'danger-text': '#14171c',
  overlay: 'rgba(0, 0, 0, 0.6)',
  'ok-fg': '#74d39b',
  'ok-bg': '#10281b',
  'ok-border': '#1f4a32',
  'warn-fg': '#f0c35c',
  'warn-bg': '#2c2209',
  'warn-border': '#4f3d13',
  'bad-fg': '#ff8f86',
  'bad-bg': '#3a1513',
  'bad-border': '#642520',
  'info-fg': '#93b6ff',
  'info-bg': '#142140',
  'info-border': '#253b6e',
  'neutral-fg': '#b3bac4',
  'neutral-bg': '#1e2228',
  'neutral-border': '#2f343c',
  'agent-fg': '#b8a8ff',
  'agent-bg': '#1f1a3f',
  'agent-border': '#372e6c',
};

/** Theme-independent scales. Keys become `--om-<group>-<key>`. */
export const scale = {
  font: {
    sans: "'Hanken Grotesk', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    mono: "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
  },
  'font-size': {
    xs: '0.75rem',
    sm: '0.875rem',
    md: '1rem',
    lg: '1.125rem',
    xl: '1.25rem',
    '2xl': '1.5rem',
    '3xl': '1.875rem',
    '4xl': '2.25rem',
    '5xl': '3rem',
  },
  'font-weight': { regular: '400', medium: '500', semibold: '600', bold: '700' },
  'line-height': { tight: '1.25', normal: '1.5' },
  space: {
    '0': '0',
    '0-5': '2px',
    '1': '4px',
    '2': '8px',
    '3': '12px',
    '4': '16px',
    '5': '20px',
    '6': '24px',
    '8': '32px',
    '10': '40px',
    '12': '48px',
    '16': '64px',
  },
  radius: { xs: '4px', sm: '6px', md: '10px', lg: '14px', xl: '20px', pill: '999px' },
  motion: {
    'duration-fast': '120ms',
    'duration-base': '180ms',
    'duration-slow': '320ms',
    'ease-standard': 'cubic-bezier(0.2, 0, 0, 1)',
    'ease-exit': 'cubic-bezier(0.3, 0, 1, 1)',
  },
  layout: {
    'content-max': '1200px',
    'nav-width': '232px',
    'tabbar-height': '64px',
    'touch-target': '44px',
    'bp-compact': '720px',
  },
  z: { nav: '10', dialog: '40', toast: '50' },
} as const;

/** Elevation: three levels. Dark mode leans on borders, so shadows are darker and tighter. */
export const shadow = {
  light: {
    '1': '0 1px 2px rgba(20, 23, 28, 0.06), 0 1px 3px rgba(20, 23, 28, 0.08)',
    '2': '0 6px 16px -6px rgba(20, 23, 28, 0.14)',
    '3': '0 24px 56px -16px rgba(20, 23, 28, 0.28)',
  },
  dark: {
    '1': '0 1px 2px rgba(0, 0, 0, 0.5)',
    '2': '0 8px 20px -6px rgba(0, 0, 0, 0.55)',
    '3': '0 28px 64px -16px rgba(0, 0, 0, 0.75)',
  },
} as const;

function block(vars: Record<string, string>, indent: string): string {
  return Object.entries(vars)
    .map(([k, v]) => `${indent}${k}: ${v};`)
    .join('\n');
}

function themeVars(t: Theme, s: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(t)) out[`--om-color-${k}`] = v;
  for (const [k, v] of Object.entries(s)) out[`--om-shadow-${k}`] = v;
  return out;
}

/** CSS custom properties for the scales (theme-independent). */
export function scaleVars(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [group, values] of Object.entries(scale)) {
    for (const [k, v] of Object.entries(values)) out[`--om-${group}-${k}`] = v;
  }
  return out;
}

/**
 * The full tokens.css. Theme selection:
 * - no `data-theme` on <html>: follow the system (prefers-color-scheme);
 * - `data-theme="light"` or `"dark"`: forced by the person's setting.
 * Reduced motion sets every duration to 0 ms.
 */
export function toCss(): string {
  const header =
    '/* SPDX-License-Identifier: Apache-2.0 */\n' +
    '/* Generated from src/tokens/tokens.ts by `npm run tokens`. Do not edit by hand. */\n';
  const lightVars = block(themeVars(light, shadow.light), '  ');
  const darkVars = block(themeVars(dark, shadow.dark), '    ');
  const darkForced = block(themeVars(dark, shadow.dark), '  ');
  return (
    header +
    `:root {\n${block(scaleVars(), '  ')}\n${lightVars}\n  color-scheme: light;\n}\n\n` +
    `@media (prefers-color-scheme: dark) {\n  :root:not([data-theme='light']) {\n${darkVars}\n    color-scheme: dark;\n  }\n}\n\n` +
    `:root[data-theme='dark'] {\n${darkForced}\n  color-scheme: dark;\n}\n\n` +
    `@media (prefers-reduced-motion: reduce) {\n  :root {\n    --om-motion-duration-fast: 0ms;\n    --om-motion-duration-base: 0ms;\n    --om-motion-duration-slow: 0ms;\n  }\n}\n`
  );
}

/** Plain JSON for non-CSS consumers (the React Native app, docs). */
export function toJson(): string {
  return JSON.stringify({ palette, light, dark, scale, shadow }, null, 2) + '\n';
}
