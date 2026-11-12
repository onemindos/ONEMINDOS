// SPDX-License-Identifier: Apache-2.0
// Store-only token extension (documented in ui/src/store/README.md). The eight app-tile hues are
// the only new raw colours. AppTile passes them to store.css as inline --om-store-a/-b/-fg custom
// properties, so this file is the single source; a test checks white text on every stop (≥ 4.5:1).
// Tiles keep their colour in both themes, like an app icon, so one pair per hue is enough.
export const TILE_HUES: readonly { name: string; a: string; b: string }[] = [
  { name: 'teal', a: '#1f6a66', b: '#113432' },
  { name: 'blue', a: '#2447b8', b: '#1a3389' },
  { name: 'violet', a: '#5b45c4', b: '#3b2a8f' },
  { name: 'green', a: '#166236', b: '#0e3f23' },
  { name: 'amber', a: '#8a5a00', b: '#5c3c00' },
  { name: 'red', a: '#b42318', b: '#7a170f' },
  { name: 'slate', a: '#475459', b: '#2b3539' },
  { name: 'plum', a: '#8e2c74', b: '#5e1c4c' },
];
export const TILE_TEXT = '#ffffff';
