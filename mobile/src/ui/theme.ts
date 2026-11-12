// SPDX-License-Identifier: Apache-2.0
// The phone's theme comes from the OneMind design tokens (ui/src/tokens/tokens.ts → tokens.generated.ts,
// docs/design/TOKENS.md): the same colour roles, spacing, radii and type scale as the dashboard.
// Screens use only these names; they never pick raw colours.
import { useColorScheme } from 'react-native';
import { tokens } from './tokens.generated';

type Roles = { [K in keyof typeof tokens.light]: string };

function fromRoles(r: Roles) {
  return {
    bg: r.bg,
    card: r.surface,
    sunken: r['surface-sunken'],
    raised: r['surface-raised'],
    text: r.text,
    muted: r['text-muted'],
    subtle: r['text-subtle'],
    border: r.border,
    borderStrong: r['border-strong'],
    accent: r.accent,
    accentText: r['accent-text'],
    accentSoft: r['accent-soft'],
    focus: r.focus,
    danger: r.danger,
    dangerText: r['danger-text'],
    ok: r['ok-fg'],
    okBg: r['ok-bg'],
    okBorder: r['ok-border'],
    warn: r['warn-fg'],
    warnBg: r['warn-bg'],
    warnBorder: r['warn-border'],
    bad: r['bad-fg'],
    badBg: r['bad-bg'],
    badBorder: r['bad-border'],
    info: r['info-fg'],
    infoBg: r['info-bg'],
    infoBorder: r['info-border'],
    neutral: r['neutral-fg'],
    neutralBg: r['neutral-bg'],
    neutralBorder: r['neutral-border'],
    /** Anything an AI agent did or asked for (docs/design/TOKENS.md). */
    agent: r['agent-fg'],
    agentBg: r['agent-bg'],
    agentBorder: r['agent-border'],
  };
}

const light = fromRoles(tokens.light);
export type Palette = typeof light;
const dark: Palette = fromRoles(tokens.dark);

export function useTheme(): Palette {
  return useColorScheme() === 'dark' ? dark : light;
}

/** px from a token value ('16px', '1.125rem'). */
const px = (v: string) => Number.parseFloat(v) * (v.endsWith('rem') ? 16 : 1);
const S = tokens.scale;

export const space = { xs: px(S.space['1']), sm: px(S.space['2']), md: px(S.space['3']), lg: px(S.space['4']), xl: px(S.space['6']) };
/** Cards use radius-lg, controls radius-md (ui/src/styles/components.css). */
export const radius = px(S.radius.lg);
export const radiusControl = px(S.radius.md);
export const touchTarget = px(S.layout['touch-target']);
export const font = {
  xs: px(S['font-size'].xs),
  sm: px(S['font-size'].sm),
  md: px(S['font-size'].md),
  lg: px(S['font-size'].lg),
  xl: px(S['font-size'].xl),
  xxl: px(S['font-size']['2xl']),
  semibold: S['font-weight'].semibold as '600',
  bold: S['font-weight'].bold as '700',
};

/** OneMind Red (brand/README.md). Only the logo uses it: red is the danger colour everywhere else. */
export const BRAND_RED = '#FF333A';
