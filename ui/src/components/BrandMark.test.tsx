// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { brand } from '../tokens/brand.generated.ts';
import { dark, light } from '../tokens/tokens';
import { BrandMark, BRAND } from './BrandMark';

describe('BrandMark', () => {
  it('is decorative by default and draws both logo layers from the brand file', () => {
    const { container } = render(<BrandMark />);
    const svg = container.querySelector('svg')!;
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('viewBox', brand.logo.viewBox);
    const paths = svg.querySelectorAll('path');
    expect(paths).toHaveLength(2);
    expect(paths[0]).toHaveAttribute('fill', 'var(--om-color-logo-brain)');
  });
  it('takes an accessible name when it stands alone', () => {
    render(<BrandMark label={BRAND.shortName} />);
    expect(screen.getByRole('img', { name: brand.shortName })).toBeInTheDocument();
  });
  it('uses the colour variant in light and the on-dark variant in dark', () => {
    expect(light['logo-brain']).toBe(brand.logo.light.brain);
    expect(dark['logo-circuit']).toBe(brand.logo.dark.circuit);
  });
});
