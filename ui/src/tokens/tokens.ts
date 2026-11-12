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

const p = palette;

/** Semantic colour roles. Every role exists in both themes. */
export type ColorRole =
  | 'bg'
  | 'surface'
  | 'surface-sunken'
  | 'surface-raised'
  | 'border'
  | 'border-strong'
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
  bg: p.neutral[25],
  surface: p.neutral[0],
  'surface-sunken': p.neutral[50],
  'surface-raised': p.neutral[0],
  border: p.neutral[100],
  'border-strong': p.neutral[200],
  text: p.neutral[900],
  'text-muted': p.neutral[600],
  'text-subtle': p.neutral[500],
  // Default accent: OneMind Red, made AA-safe for this theme by scripts/brand-sync.py.
  accent: brand.accent.light.accent,
  'accent-hover': brand.accent.light.hover,
  'accent-text': brand.accent.light.text,
  'accent-soft': brand.accent.light.soft,
  'logo-brain': brand.logo.light.brain,
  'logo-circuit': brand.logo.light.circuit,
  focus: p.blue[600],
  danger: p.red[600],
  'danger-hover': p.red[700],
  'danger-text': p.neutral[0],
  overlay: 'rgba(12, 18, 20, 0.48)',
  'ok-fg': p.green[700],
  'ok-bg': p.green[50],
  'ok-border': p.green[100],
  'warn-fg': p.amber[700],
  'warn-bg': p.amber[50],
  'warn-border': p.amber[100],
  'bad-fg': p.red[700],
  'bad-bg': p.red[50],
  'bad-border': p.red[100],
  'info-fg': p.blue[700],
  'info-bg': p.blue[50],
  'info-border': p.blue[100],
  'neutral-fg': p.neutral[600],
  'neutral-bg': p.neutral[50],
  'neutral-border': p.neutral[100],
  'agent-fg': p.violet[700],
  'agent-bg': p.violet[50],
  'agent-border': p.violet[100],
};

export const dark: Theme = {
  bg: p.neutral[950],
  surface: p.neutral[900],
  'surface-sunken': '#0f1517',
  'surface-raised': p.neutral[850],
  border: p.neutral[800],
  'border-strong': p.neutral[700],
  text: '#e8eeef',
  'text-muted': '#a9b6b9',
  'text-subtle': '#8a989c',
  accent: brand.accent.dark.accent,
  'accent-hover': brand.accent.dark.hover,
  'accent-text': brand.accent.dark.text,
  'accent-soft': brand.accent.dark.soft,
  'logo-brain': brand.logo.dark.brain,
  'logo-circuit': brand.logo.dark.circuit,
  focus: p.blue[300],
  danger: p.red[300],
  'danger-hover': '#ffb0a9',
  'danger-text': p.neutral[950],
  overlay: 'rgba(0, 0, 0, 0.6)',
  'ok-fg': p.green[300],
  'ok-bg': '#10291a',
  'ok-border': '#1d4a2e',
  'warn-fg': p.amber[300],
  'warn-bg': '#2e2309',
  'warn-border': '#523f12',
  'bad-fg': p.red[300],
  'bad-bg': '#3a1512',
  'bad-border': '#63231d',
  'info-fg': p.blue[300],
  'info-bg': '#15213f',
  'info-border': '#253a70',
  'neutral-fg': '#b5c0c3',
  'neutral-bg': p.neutral[850],
  'neutral-border': '#2a353a',
  'agent-fg': p.violet[300],
  'agent-bg': '#1f1940',
  'agent-border': '#382d70',
};

/** Theme-independent scales. Keys become `--om-<group>-<key>`. */
export const scale = {
  font: {
    sans: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    mono: "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
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
    'duration-base': '200ms',
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
    '1': '0 1px 2px rgba(19, 26, 29, 0.06), 0 1px 3px rgba(19, 26, 29, 0.08)',
    '2': '0 4px 8px -2px rgba(19, 26, 29, 0.08), 0 8px 20px -4px rgba(19, 26, 29, 0.12)',
    '3': '0 12px 24px -6px rgba(19, 26, 29, 0.16), 0 24px 48px -12px rgba(19, 26, 29, 0.24)',
  },
  dark: {
    '1': '0 1px 2px rgba(0, 0, 0, 0.4)',
    '2': '0 4px 12px -2px rgba(0, 0, 0, 0.5)',
    '3': '0 16px 40px -8px rgba(0, 0, 0, 0.7)',
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
