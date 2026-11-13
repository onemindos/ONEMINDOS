// SPDX-License-Identifier: Apache-2.0
// Generated from brand/brand.json by scripts/brand-sync.py. Do not edit by hand.
import markColor from './assets/brand/onemind-mark-color.svg';
import markOnDark from './assets/brand/onemind-mark-on-dark.svg';

export const brand = {
  name: "OneMind OS",
  shortName: "OneMind",
  tagline: "AI can ask. Only you approve.",
  logo: { alt: "OneMind", color: markColor, onDark: markOnDark },
} as const;
