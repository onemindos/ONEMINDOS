// SPDX-License-Identifier: Apache-2.0
// The wallpaper behind the whole app. Rendered into <body> behind everything (z-index -1),
// in both theme variants; CSS shows the one that matches the current theme, so switching
// light/dark never waits for JavaScript. A veil in the page colour dims it to the level the
// contrast guard requires (--om-wallpaper-dim, set by customizeCss()).
import { createPortal } from 'react-dom';
import type { CSSProperties } from 'react';
import { useOptionalCustomize } from './CustomizeProvider';
import type { AppearancePreferences } from './preferences';
import { wallpaperBackground } from './wallpapers';

/** CSS backgrounds for one wallpaper choice: [light, dark], or null for none. */
export function wallpaperLayers(choice: AppearancePreferences['wallpaper'], image: string | null): [string, string] | null {
  if (choice === 'none') return null;
  if (choice === 'custom') {
    if (!image || !image.startsWith('data:image/')) return null;
    const bg = `url("${image.replace(/"/g, '%22')}") center / cover no-repeat`;
    return [bg, bg];
  }
  return [wallpaperBackground(choice, 'light'), wallpaperBackground(choice, 'dark')];
}

/** Visual of a wallpaper at any size: used by the layer and by the picker tiles. */
export function WallpaperSurface({ layers, className, style }: { layers: [string, string]; className?: string; style?: CSSProperties }) {
  return (
    <span className={className} style={style} aria-hidden="true">
      <span className="om-cz-wp om-cz-wp-light" style={{ background: layers[0] }} />
      <span className="om-cz-wp om-cz-wp-dark" style={{ background: layers[1] }} />
    </span>
  );
}

export function WallpaperLayer({ portal = true }: { portal?: boolean }) {
  const ctx = useOptionalCustomize();
  if (!ctx || ctx.status.phase === 'loading') return null;
  const layers = wallpaperLayers(ctx.prefs.wallpaper, ctx.wallpaperImage);
  if (!layers) return null;
  const node = (
    <div className="om-cz-wallpaper" aria-hidden="true" data-wallpaper={ctx.prefs.wallpaper}>
      <WallpaperSurface layers={layers} className="om-cz-wallpaper-img" />
      <span className="om-cz-wallpaper-veil" />
    </div>
  );
  return portal && typeof document !== 'undefined' ? createPortal(node, document.body) : node;
}
