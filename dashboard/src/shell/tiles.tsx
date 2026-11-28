// SPDX-License-Identifier: Apache-2.0
// Screen tiles and the count badge, shared by the dock and the launcher.
import { Icon, type NavItem } from '@onemind/ui';

/**
 * Atlas's muted tiles (founder pick 2026-11-21: icons and tiles follow Atlas; illustrated system tiles come later as
 * original artwork): a neutral tile in the theme's surface colour with an ink glyph, never one bright hue per screen.
 * The colours come from the design tokens in desktop.css, so the Sovereign palette applies without a change here.
 */
export function ScreenTile({ id, icon, size = 44 }: { id: string; icon: NavItem['icon']; size?: number }) {
  return (
    <span className="dsk-tile" data-screen={id} style={{ width: size, height: size }} aria-hidden="true">
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

