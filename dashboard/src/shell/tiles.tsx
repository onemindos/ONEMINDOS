// SPDX-License-Identifier: Apache-2.0
// Screen tiles and the count badge, shared by the dock and the launcher.
import type { CSSProperties } from 'react';
import { Icon, type NavItem } from '@onemind/ui';
import { HUES } from '../screens/registry';

/** One colour per screen (each screen's `hue`), so a place is recognised before its name is read. White glyph on each. */
export const SCREEN_HUES = HUES;

const FALLBACK_HUE = ['#7d8794', '#3a414b'] as const;

export function tileStyle(id: string): CSSProperties {
  const [a, b] = SCREEN_HUES[id] ?? FALLBACK_HUE;
  return { '--dsk-tile-a': a, '--dsk-tile-b': b } as CSSProperties;
}


export function ScreenTile({ id, icon, size = 44 }: { id: string; icon: NavItem['icon']; size?: number }) {
  return (
    <span className="dsk-tile" style={{ ...tileStyle(id), width: size, height: size }} aria-hidden="true">
      <Icon name={icon} size={Math.round(size * 0.48)} />
    </span>
  );
}

export function Badge({ item }: { item: NavItem }) {
  if (!item.badge) return null;
  return (
    <span className="dsk-badge">
      <span aria-hidden="true">{item.badge}</span>
      <span className="om-visually-hidden">{item.badgeLabel ?? `${item.badge} new`}</span>
    </span>
  );
}

