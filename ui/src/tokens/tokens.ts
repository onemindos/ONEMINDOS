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
    25: '#f2f5f6',
    50: '#e9eef0',
    100: '#d9e1e4',
    200: '#bccacf',
    300: '#7a8d95',
    400: '#566a73',
    500: '#3f545e',
    600: '#2d4651',
    700: '#1d3038',
    800: '#15262d',
    850: '#0f1c22',
    900: '#081013',
    950: '#0a1418',
  },
  lantern: { 200: '#ffc79f', 300: '#ffb27a', 600: '#a8470f', 700: '#8a3a0c' },
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

// Direction C "Lantern": dark-first deep ink-teal with a warm apricot accent. The light theme is
// porcelain. Logo colours stay the brand's (brand/brand.json); the accent is Lantern, not brand red.
export const light: Theme = {
  bg: '#f2f5f6',
  surface: '#ffffff',
  'surface-sunken': '#e9eef0',
  'surface-raised': '#ffffff',
  border: '#d9e1e4',
  'border-strong': '#bccacf',
  'control-border': '#7a8d95',
  text: '#0d1b22',
  'text-muted': '#3f545e',
  'text-subtle': '#566a73',
  accent: '#a8470f',
  'accent-hover': '#8a3a0c',
  'accent-text': '#ffffff',
  'accent-soft': '#fbeadf',
  'logo-brain': brand.logo.light.brain,
  'logo-circuit': brand.logo.light.circuit,
  focus: '#1d6fb8',
  danger: '#b4231c',
  'danger-hover': '#8f1b15',
  'danger-text': '#ffffff',
  overlay: 'rgba(8, 20, 26, 0.45)',
  'ok-fg': '#11634b',
  'ok-bg': '#e2f4ee',
  'ok-border': '#bfe4d6',
  // Attention is olive-yellow so it never blurs into the apricot accent; it always carries its icon.
  'warn-fg': '#5e5300',
  'warn-bg': '#f6f1cc',
  'warn-border': '#e4da93',
  'bad-fg': '#a3201b',
  'bad-bg': '#fcebe9',
  'bad-border': '#f4cac6',
  'info-fg': '#1d5d99',
  'info-bg': '#e5effa',
  'info-border': '#c6dbf1',
  'neutral-fg': '#3f545e',
  'neutral-bg': '#e9eef0',
  'neutral-border': '#d2dce0',
  'agent-fg': '#4d3b9c',
  'agent-bg': '#eeebfb',
  'agent-border': '#d8d1f4',
};

export const dark: Theme = {
  bg: '#0a1418',
  surface: '#0f1c22',
  'surface-sunken': '#081013',
  'surface-raised': '#15262d',
  border: '#1d3038',
  'border-strong': '#2d4651',
  'control-border': '#4f6c78',
  text: '#e6f0f2',
  'text-muted': '#a3b7be',
  'text-subtle': '#869ba3',
  accent: '#ffb27a',
  'accent-hover': '#ffc79f',
  'accent-text': '#0a1418',
  'accent-soft': '#3a2a1f',
  'logo-brain': brand.logo.dark.brain,
  'logo-circuit': brand.logo.dark.circuit,
  focus: '#7cc4ff',
  danger: '#ff8b7f',
  'danger-hover': '#ffaca3',
  'danger-text': '#0a1418',
  overlay: 'rgba(2, 8, 10, 0.66)',
  'ok-fg': '#6fdcb4',
  'ok-bg': '#0e2a22',
  'ok-border': '#1a4a3b',
  'warn-fg': '#e9dc6a',
  'warn-bg': '#29270b',
  'warn-border': '#4a4615',
  'bad-fg': '#ff8b7f',
  'bad-bg': '#3a1614',
  'bad-border': '#632521',
  'info-fg': '#8cc2ff',
  'info-bg': '#10243c',
  'info-border': '#1e406a',
  'neutral-fg': '#b0c2c8',
  'neutral-bg': '#15262d',
  'neutral-border': '#263c45',
  'agent-fg': '#b9a9ff',
  'agent-bg': '#1d1a40',
  'agent-border': '#352f6e',
};

/** Theme-independent scales. Keys become `--om-<group>-<key>`. */
export const scale = {
  font: {
    sans: "'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
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
  'line-height': { tight: '1.25', normal: '1.5', relaxed: '1.55' },
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
  radius: { xs: '4px', sm: '6px', md: '12px', lg: '18px', xl: '24px', pill: '999px' },
  motion: {
    'duration-fast': '120ms',
    'duration-base': '200ms',
    'duration-slow': '320ms',
    'ease-standard': 'cubic-bezier(0.16, 1, 0.3, 1)',
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

/** Elevation: three levels. Light shadows are tinted ink-teal; dark leans on lightness steps and borders. */
export const shadow = {
  light: {
    '1': '0 1px 2px rgba(10, 30, 40, 0.07), 0 1px 3px rgba(10, 30, 40, 0.08)',
    '2': '0 8px 22px -8px rgba(10, 30, 40, 0.18)',
    '3': '0 30px 70px -18px rgba(10, 30, 40, 0.32)',
  },
  dark: {
    '1': '0 1px 2px rgba(0, 0, 0, 0.5)',
    '2': '0 10px 28px -10px rgba(0, 0, 0, 0.6)',
    '3': '0 32px 80px -20px rgba(0, 0, 0, 0.8)',
  },
} as const;

/** The lantern glow: used only on the focused or selected primary element and on "Needs you". */
export const glow = {
  light: '0 0 0 1px rgba(168, 71, 15, 0.22), 0 8px 28px -10px rgba(168, 71, 15, 0.28)',
  dark: '0 0 0 1px rgba(255, 178, 122, 0.25), 0 8px 32px -8px rgba(255, 178, 122, 0.35)',
} as const;

function block(vars: Record<string, string>, indent: string): string {
  return Object.entries(vars)
    .map(([k, v]) => `${indent}${k}: ${v};`)
    .join('\n');
}

function themeVars(t: Theme, s: Record<string, string>, g: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(t)) out[`--om-color-${k}`] = v;
  for (const [k, v] of Object.entries(s)) out[`--om-shadow-${k}`] = v;
  out['--om-glow-accent'] = g;
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
  const lightVars = block(themeVars(light, shadow.light, glow.light), '  ');
  const darkVars = block(themeVars(dark, shadow.dark, glow.dark), '    ');
  const darkForced = block(themeVars(dark, shadow.dark, glow.dark), '  ');
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
  return JSON.stringify({ palette, light, dark, scale, shadow, glow }, null, 2) + '\n';
}
