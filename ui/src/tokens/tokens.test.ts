// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import committedCss from './tokens.css?raw';
import { dark, light, TONES, toCss, toJson, type Theme } from './tokens';

function lum(hex: string): number {
  const n = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}
function contrast(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m);
  return (x! + 0.05) / (y! + 0.05);
}

describe('tokens', () => {
  it('tokens.css is generated from tokens.ts (run `npm run tokens` after editing)', () => {
    expect(committedCss).toBe(toCss());
  });

  it('both themes define the same roles', () => {
    expect(Object.keys(dark).sort()).toEqual(Object.keys(light).sort());
  });

  it('JSON export round-trips', () => {
    expect(JSON.parse(toJson()).light.accent).toBe(light.accent);
  });

  // WCAG 2.2 AA: 4.5:1 for body text, 3:1 for UI component boundaries and focus (1.4.11).
  describe.each([
    ['light', light],
    ['dark', dark],
  ] as Array<[string, Theme]>)('%s theme contrast', (_name, t) => {
    it.each([
      ['text', 'bg'],
      ['text', 'surface'],
      ['text', 'surface-sunken'],
      ['text', 'surface-raised'],
      ['text-muted', 'bg'],
      ['text-muted', 'surface'],
      ['text-muted', 'surface-sunken'],
      ['text-subtle', 'surface'],
      ['accent', 'surface'],
      ['accent', 'bg'],
      ['accent', 'accent-soft'],
      ['accent-text', 'accent'],
      ['danger-text', 'danger'],
    ] as Array<[keyof Theme, keyof Theme]>)('%s on %s ≥ 4.5', (fg, bg) => {
      expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5);
    });

    it.each(TONES.map((tone) => [tone]))('%s pill text ≥ 4.5 on its own background and on surface', (tone) => {
      const fg = t[`${tone}-fg` as keyof Theme];
      expect(contrast(fg, t[`${tone}-bg` as keyof Theme])).toBeGreaterThanOrEqual(4.5);
      expect(contrast(fg, t.surface)).toBeGreaterThanOrEqual(4.5);
    });

    it('focus ring ≥ 3 against bg and surface', () => {
      expect(contrast(t.focus, t.bg)).toBeGreaterThanOrEqual(3);
      expect(contrast(t.focus, t.surface)).toBeGreaterThanOrEqual(3);
    });
  });
});
