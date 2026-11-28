// SPDX-License-Identifier: Apache-2.0
// Snap layouts (Atlas 01b): a small flyout on a window's maximise button. Each thumbnail is a layout,
// each part of it a button that puts the window there. Opens on hover or with the down arrow on the
// maximise button; Esc closes it and gives focus back.
import { useState, type KeyboardEvent } from 'react';
import type { Rect } from './store';
import { SNAP_LAYOUTS } from './tiling';

interface Props {
  id: string;
  title: string;
  /** Focus the first zone when it opens (opened from the keyboard). */
  focusFirst: boolean;
  onSnap(rect: Rect): void;
  onClose(refocus: boolean): void;
}

export function SnapFlyout({ id, title, focusFirst, onSnap, onClose }: Props) {
  const [hint, setHint] = useState<string>();
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== 'Escape') return;
    // Taken here, so Esc closes the flyout and not the window.
    e.preventDefault();
    e.stopPropagation();
    onClose(true);
  }
  return (
    <div id={id} className="wm-snap" role="group" aria-label={`Snap ${title}`} onKeyDown={onKeyDown}>
      <div className="wm-snap-layouts">
        {SNAP_LAYOUTS.map((layout, l) => (
          <div key={layout.id} className="wm-snap-layout" data-layout={layout.id}>
            {layout.zones.map((zone, z) => {
              const label = `${title} ${zone.where}`;
              return (
                <button key={zone.where} type="button" className="wm-snap-zone" style={{ flexGrow: zone.rect.width }} aria-label={label} data-on={hint === label || undefined}
                  autoFocus={focusFirst && l === 0 && z === 0}
                  onPointerEnter={() => setHint(label)} onFocus={() => setHint(label)} onClick={() => onSnap(zone.rect)} />
              );
            })}
          </div>
        ))}
      </div>
      <p className="wm-snap-hint" aria-hidden="true">
        <span>{hint ?? 'Pick a place'}</span>
        <kbd>Alt Shift ← →</kbd>
      </p>
    </div>
  );
}
