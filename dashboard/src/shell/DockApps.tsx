// SPDX-License-Identifier: Apache-2.0
// The dock's pinned apps. With the run bar switched on, the first apps stay and the rest move into a "More" item that
// names them (final design 09: "Nothing disappears silently"); More opens the launcher, which lists every app.
import { AppIcon, Icon } from '@onemind/ui';
import type { DockApp } from './DesktopShell';
import { makeRoomForRunBar } from './dock';

export function DockApps({ apps, runBar, onMore }: { apps: DockApp[]; runBar: boolean; onMore: () => void }) {
  const { shown, moved } = makeRoomForRunBar(apps, runBar);
  if (shown.length === 0 && moved.length === 0) return null;
  const names = moved.map((a) => a.name).join(', ');
  return (
    <>
      <span className="dsk-dock-sep" aria-hidden="true" />
      <ul className="dsk-dock-group" aria-label="Pinned apps">
        {shown.map((a) => (
          <li key={a.id}>
            <a href={a.href} className="dsk-dock-item dsk-dock-app">
              <AppIcon app={a} size={44} />
              <span className="dsk-dock-label">{a.name}</span>
            </a>
          </li>
        ))}
        {moved.length > 0 && (
          <li>
            <button type="button" className="dsk-dock-item" aria-haspopup="dialog" onClick={onMore} aria-label={`More: ${names} (moved to make room for the run bar)`} title={`Moved here to make room for the run bar: ${names}`}>
              <span className="dsk-tile dsk-tile-more" aria-hidden="true">
                <Icon name="menu" size={20} />
                <span className="dsk-more-count">{moved.length}</span>
              </span>
              <span className="dsk-dock-label" aria-hidden="true">More</span>
            </button>
          </li>
        )}
      </ul>
    </>
  );
}
