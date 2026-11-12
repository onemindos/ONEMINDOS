// SPDX-License-Identifier: Apache-2.0
// One app icon for every screen (CRITIQUE #20): Home, the Store, the jobs tray and the approval
// card all draw the same tile, so one app never looks like two brands. Uses the manifest `icon`
// when it is an http(s) or same-origin path; otherwise a monogram on a hue picked from the app id.
import type { CSSProperties } from 'react';
import { safeHttpUrl } from '../lib/trust';

/**
 * The eight tile hues (each a gradient pair). Tiles keep their colour in both themes, like an
 * app icon. White monogram text is ≥ 4.5:1 on both stops of every hue (store/logic.test.ts).
 */
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

/** A stable tile hue 0-7 from the app id, so an app keeps its colour everywhere. */
export function tileHue(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h % 8;
}

/** "Home Assistant" → "HA", "ntfy" → "N". */
export function monogram(name: string): string {
  const words = name.split(/[\s._-]+/).filter(Boolean);
  if (words.length >= 2) return (words[0]![0]! + words[1]![0]!).toUpperCase();
  return (words[0]?.[0] ?? '?').toUpperCase();
}

export interface AppIconProps {
  app: { id: string; name: string; icon?: string | null };
  size?: number;
  className?: string;
}

/** Decorative (aria-hidden): the app's name is always written next to it. */
export function AppIcon({ app, size = 48, className }: AppIconProps) {
  const src = app.icon && (app.icon.startsWith('/') && !app.icon.startsWith('//') ? app.icon : safeHttpUrl(app.icon));
  const hue = TILE_HUES[tileHue(app.id)]!;
  return (
    <span
      className={className ? `om-app-icon ${className}` : 'om-app-icon'}
      data-hue={hue.name}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38), '--om-app-icon-a': hue.a, '--om-app-icon-b': hue.b, '--om-app-icon-fg': TILE_TEXT } as CSSProperties}
      aria-hidden="true"
    >
      {src ? <img src={src} alt="" width={size} height={size} loading="lazy" /> : monogram(app.name)}
    </span>
  );
}
