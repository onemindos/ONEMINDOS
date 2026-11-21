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
    25: '#f5f3f0',
    50: '#eeebe6',
    100: '#e4dfd8',
    200: '#cbc3b8',
    300: '#aaa093',
    400: '#8c8176',
    500: '#6b6158',
    600: '#564d45',
    700: '#4a4038',
    800: '#332b25',
    850: '#26201b',
    900: '#1e1915',
    950: '#16120f',
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
  // Hearth (direction B): warm stone neutrals (OKLCH hue ~65, chroma <= 0.015), Ember accent.
  bg: '#f5f3f0',
  surface: '#fffefc',
  'surface-sunken': '#eeebe6',
  'surface-raised': '#ffffff',
  border: '#e4dfd8',
  'border-strong': '#cbc3b8',
  'control-border': '#8c8176',
  text: '#1f1a16',
  'text-muted': '#564d45',
  'text-subtle': '#6b6158',
  // Ember: a deepened OneMind red. The logo keeps the brand colours.
  accent: '#b3202c',
  'accent-hover': '#941823',
  'accent-text': '#ffffff',
  'accent-soft': '#f8e6e4',
  'logo-brain': brand.logo.light.brain,
  'logo-circuit': brand.logo.light.circuit,
  // Teal focus ring: reads apart from Ember.
  focus: '#0e6b72',
  // Critical is raspberry crimson, cooler than Ember so the two cannot be confused.
  danger: '#a1123f',
  'danger-hover': '#7f0e32',
  'danger-text': '#ffffff',
  overlay: 'rgba(31, 26, 22, 0.42)',
  'ok-fg': '#2f6125',
  'ok-bg': '#ebf3e3',
  'ok-border': '#cfe2bd',
  'warn-fg': '#6f4600',
  'warn-bg': '#fbefd6',
  'warn-border': '#eed6a1',
  'bad-fg': '#9a1240',
  'bad-bg': '#fbe9ef',
  'bad-border': '#f2c9d6',
  'info-fg': '#1f5679',
  'info-bg': '#e5f0f6',
  'info-border': '#c3dce9',
  'neutral-fg': '#564d45',
  'neutral-bg': '#eeebe6',
  'neutral-border': '#dcd5cc',
  'agent-fg': '#5a3a8c',
  'agent-bg': '#f0eaf8',
  'agent-border': '#ddd0ee',
};

export const dark: Theme = {
  // Lamplight: brown-black, not black.
  bg: '#16120f',
  surface: '#1e1915',
  'surface-sunken': '#120f0c',
  'surface-raised': '#26201b',
  border: '#332b25',
  'border-strong': '#4a4038',
  'control-border': '#7a6d61',
  text: '#f1ebe4',
  'text-muted': '#c0b4a7',
  'text-subtle': '#a39689',
  accent: '#f2685c',
  'accent-hover': '#f78c82',
  'accent-text': '#16120f',
  'accent-soft': '#3e2420',
  'logo-brain': brand.logo.dark.brain,
  'logo-circuit': brand.logo.dark.circuit,
  focus: '#8fc6cf',
  danger: '#f58aa8',
  'danger-hover': '#f9a9c0',
  'danger-text': '#16120f',
  overlay: 'rgba(8, 5, 3, 0.62)',
  'ok-fg': '#9fd48a',
  'ok-bg': '#182615',
  'ok-border': '#2c4524',
  'warn-fg': '#f0c46a',
  'warn-bg': '#2e230e',
  'warn-border': '#503d18',
  'bad-fg': '#f58aa8',
  'bad-bg': '#3a1522',
  'bad-border': '#62233a',
  'info-fg': '#8cc4e3',
  'info-bg': '#13242f',
  'info-border': '#22404f',
  'neutral-fg': '#c0b4a7',
  'neutral-bg': '#26201b',
  'neutral-border': '#3a322b',
  'agent-fg': '#c4abf2',
  'agent-bg': '#251c38',
  'agent-border': '#3f3060',
};

/** Theme-independent scales. Keys become `--om-<group>-<key>`. */
export const scale = {
  font: {
    sans: "Figtree, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    display: "'Bricolage Grotesque', Figtree, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    mono: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
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
  radius: { xs: '4px', sm: '8px', md: '12px', lg: '16px', xl: '24px', pill: '999px' },
  motion: {
    'duration-fast': '120ms',
    'duration-base': '200ms',
    'duration-slow': '320ms',
    'duration-open': '240ms',
    'duration-close': '160ms',
    'ease-settle': 'cubic-bezier(0.2, 0.9, 0.25, 1)',
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

/** Elevation: three levels. Light shadows are umber-tinted (warm); dark mode leans on borders. */
export const shadow = {
  light: {
    '1': '0 1px 2px rgba(60, 40, 25, 0.07), 0 1px 3px rgba(60, 40, 25, 0.08)',
    '2': '0 8px 20px -8px rgba(60, 40, 25, 0.18)',
    '3': '0 28px 60px -18px rgba(60, 40, 25, 0.30)',
  },
  dark: {
    '1': '0 1px 2px rgba(0, 0, 0, 0.45)',
    '2': '0 10px 24px -8px rgba(0, 0, 0, 0.55)',
    '3': '0 30px 70px -18px rgba(0, 0, 0, 0.7)',
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
