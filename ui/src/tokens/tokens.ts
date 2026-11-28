// SPDX-License-Identifier: Apache-2.0
// OneMind design tokens: the single source of truth (docs/design/TOKENS.md).
// `npm run tokens` writes src/tokens/tokens.css from this file; a unit test fails when they drift.
// Mobile (React Native) reads the same values from dist/tokens.json.
// Its only import is the generated brand file (brand/brand.json via scripts/brand-sync.py), with
// an explicit .ts extension so Node can run the generator on it directly.
import { brand } from './brand.generated.ts';

/** Raw colour ramps. Components never use these; they use the semantic roles below.
 * The UI roles use Sovereign's colours from the founder's final design (picks of 2026-11-21):
 * `stone` for light, `night` for dark, one signal red for every button in both modes, teal for
 * the highlight. `neutral` is the earlier warm ramp: scripts/brand-sync.py still derives the
 * website accent against it, so it stays here unchanged. */
export const palette = {
  stone: { 0: '#ffffff', 25: '#fafaf8', 50: '#f2f1ee', 75: '#ecebe7', 100: '#e8e7e3', 200: '#d9d8d3', 300: '#c4c3bd', 400: '#76777c', 500: '#5e5f64', 600: '#44454a', 900: '#17181a' },
  night: { 50: '#f3f2ef', 100: '#cdcdd0', 200: '#a6a7ac', 400: '#7c7d83', 600: '#3d3e44', 700: '#2e2f34', 750: '#26272c', 800: '#232428', 850: '#1e1f23', 900: '#17181b', 950: '#0d0e10' },
  // Signal red: 600 is the button colour (white on it 5.53:1); 700 and 300 are the red that passes
  // AA as text ("needs you"); `mark` is the logo red, used only inside the logo files.
  signal: { 300: '#ff6a6f', 600: '#cc1f2b', 700: '#b8141f', mark: '#ff333a' },
  neutral: {
    0: '#ffffff',
    25: '#fafaf9',
    50: '#f5f5f4',
    100: '#e7e5e4',
    200: '#d6d3d1',
    300: '#a8a29e',
    400: '#857e79',
    500: '#625c57',
    600: '#504a46',
    700: '#423c38',
    800: '#302b28',
    850: '#24211f',
    900: '#191715',
    950: '#151311',
  },
  // Highlight teal of the final design: 600 on light, 300 on dark.
  teal: { 50: '#e8f4f3', 100: '#cce8e5', 200: '#9fd2cc', 300: '#5fc4cb', 500: '#237d77', 600: '#1e6870', 700: '#1b5653', 900: '#113432' },
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
  | 'surface-2'
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
  | 'action'
  | 'action-hover'
  | 'action-text'
  | 'focus'
  | 'danger'
  | 'danger-hover'
  | 'danger-text'
  | 'overlay'
  | 'needs'
  | 'fault'
  | 'plugin-layer'
  | 'network-layer'
  | 'simulated'
  | 'window-edge'
  | `state-${LiveState}`
  | `${Tone}-fg`
  | `${Tone}-bg`
  | `${Tone}-border`;

/** Status tones. `agent` marks anything an AI agent did or asked for. */
export const TONES = ['ok', 'warn', 'bad', 'info', 'neutral', 'agent'] as const;
export type Tone = (typeof TONES)[number];

/** The six realtime states of the final design. Each always shows a word and a shape; colour is the third cue. */
export const LIVE_STATES = ['live', 'paused', 'retrying', 'polling', 'never', 'waiting'] as const;
export type LiveState = (typeof LIVE_STATES)[number];

export type Theme = Record<ColorRole, string>;

export const light: Theme = {
  bg: p.stone[100],
  surface: p.stone[25],
  'surface-2': p.stone[50],
  'surface-sunken': p.stone[75],
  'surface-raised': p.stone[0],
  border: p.stone[200],
  'border-strong': p.stone[300],
  // Edge of an input, chip or switch: 3:1 on every surface (WCAG 1.4.11), unlike the decorative borders above.
  'control-border': p.stone[400],
  text: p.stone[900],
  'text-muted': p.stone[600],
  'text-subtle': p.stone[500],
  // Selection, focus and navigation use the teal highlight. Buttons use signal red.
  // accent-hover and accent-soft are what deriveAccent() builds from the teal (customize/accents.ts).
  accent: p.teal[600],
  'accent-hover': '#01575f',
  'accent-text': '#ffffff',
  'accent-soft': '#e4ebea',
  action: p.signal[600],
  'action-hover': p.signal[700],
  'action-text': '#ffffff',
  'logo-brain': brand.logo.light.brain,
  'logo-circuit': brand.logo.light.circuit,
  focus: p.teal[600],
  danger: p.red[600],
  'danger-hover': p.red[700],
  'danger-text': '#ffffff',
  overlay: 'rgba(12, 18, 20, 0.48)',
  needs: p.signal[700],
  fault: '#a3420f',
  'plugin-layer': '#6a4bc4',
  'network-layer': '#2f55b8',
  simulated: p.stone[600],
  'window-edge': p.stone[900],
  'state-live': '#1a6e3e',
  'state-paused': '#8a5100',
  'state-retrying': '#8a5100',
  'state-polling': '#1a6e3e',
  'state-never': p.stone[500],
  'state-waiting': p.stone[600],
  // Sovereign's fresh and stale, darkened to pass 4.5:1 on the stone background (design departure).
  'ok-fg': '#1a6e3e',
  'ok-bg': p.green[50],
  'ok-border': p.green[100],
  'warn-fg': '#8a5100',
  'warn-bg': p.amber[50],
  'warn-border': p.amber[100],
  'bad-fg': p.signal[700],
  'bad-bg': p.red[50],
  'bad-border': p.red[100],
  'info-fg': p.blue[700],
  'info-bg': p.blue[50],
  'info-border': p.blue[100],
  'neutral-fg': p.stone[500],
  'neutral-bg': p.stone[50],
  'neutral-border': p.stone[200],
  'agent-fg': p.violet[700],
  'agent-bg': p.violet[50],
  'agent-border': p.violet[100],
};

export const dark: Theme = {
  bg: p.night[950],
  surface: p.night[900],
  'surface-2': p.night[850],
  // Lighter than the surface on purpose (design departure): wells and tracks stay visible.
  'surface-sunken': p.night[750],
  'surface-raised': p.night[800],
  border: p.night[700],
  'border-strong': p.night[600],
  'control-border': p.night[400],
  text: p.night[50],
  'text-muted': p.night[100],
  'text-subtle': p.night[200],
  accent: p.teal[300],
  'accent-hover': '#77dbe2',
  'accent-text': p.night[950],
  'accent-soft': '#24373b',
  // The same signal red with white text as in light mode: one button colour on every device.
  action: p.signal[600],
  'action-hover': p.signal[700],
  'action-text': '#ffffff',
  'logo-brain': brand.logo.dark.brain,
  'logo-circuit': brand.logo.dark.circuit,
  focus: p.teal[300],
  danger: p.red[300],
  'danger-hover': '#ffb0a9',
  'danger-text': p.night[950],
  overlay: 'rgba(0, 0, 0, 0.6)',
  needs: p.signal[300],
  fault: '#ff8a4c',
  'plugin-layer': '#b9a2ff',
  'network-layer': '#8fb4ff',
  simulated: p.night[100],
  'window-edge': p.night[50],
  'state-live': '#5bc98a',
  'state-paused': '#f2b45a',
  'state-retrying': '#f2b45a',
  'state-polling': '#5bc98a',
  'state-never': p.night[200],
  'state-waiting': p.night[100],
  'ok-fg': '#5bc98a',
  'ok-bg': '#10291a',
  'ok-border': '#1d4a2e',
  'warn-fg': '#f2b45a',
  'warn-bg': '#2e2309',
  'warn-border': '#523f12',
  'bad-fg': p.signal[300],
  'bad-bg': '#3a1512',
  'bad-border': '#63231d',
  'info-fg': p.blue[300],
  'info-bg': '#15213f',
  'info-border': '#253a70',
  'neutral-fg': p.night[200],
  'neutral-bg': p.night[800],
  'neutral-border': p.night[700],
  'agent-fg': p.violet[300],
  'agent-bg': '#1f1940',
  'agent-border': '#382d70',
};

/** Theme-independent scales. Keys become `--om-<group>-<key>`. */
export const scale = {
  font: {
    sans: "'Inter Variable', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
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
  radius: { xs: '6px', sm: '8px', md: '12px', lg: '16px', xl: '22px', pill: '999px' },
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
    'window-radius': '14px',
    'strip-height': '38px',
    'window-bar-height': '42px',
    'dock-clearance': '104px',
    'tile-radius': '26%',
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
