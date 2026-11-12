// SPDX-License-Identifier: Apache-2.0
// The OneMind logo, drawn inline from the generated brand file (brand/brand.json via
// scripts/brand-sync.py). Its two layers take the `logo-brain` and `logo-circuit` colour
// roles, so it shows the colour variant in the light theme and the on-dark variant in the
// dark theme without any image file. The mark is a trademark (brand/README.md).
import { brand } from '../tokens/brand.generated.ts';

export interface BrandMarkProps {
  /** Pixel size of the square mark. */
  size?: number;
  className?: string;
  /** Accessible name. Leave empty when the name is also written next to the mark. */
  label?: string;
}

export function BrandMark({ size = 28, className, label }: BrandMarkProps) {
  const named = Boolean(label);
  return (
    <svg
      className={className}
      viewBox={brand.logo.viewBox}
      width={size}
      height={size}
      role={named ? 'img' : undefined}
      aria-label={named ? label : undefined}
      aria-hidden={named ? undefined : true}
      focusable="false"
    >
      <path fill="var(--om-color-logo-brain)" fillRule="evenodd" d={brand.logo.brain} />
      <path fill="var(--om-color-logo-circuit)" fillRule="evenodd" d={brand.logo.circuit} />
    </svg>
  );
}

/** Product names from brand/brand.json. */
export const BRAND = { name: brand.name, shortName: brand.shortName, tagline: brand.tagline } as const;
