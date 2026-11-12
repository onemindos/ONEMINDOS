// SPDX-License-Identifier: Apache-2.0
// The dock: apps the person pinned, always within reach at the bottom of Home. On phones
// it floats above the tab bar. Reordering works with buttons in edit mode.
import { Icon } from '../components/Icon';
import { movePin, type HomeLayout } from './layout';
import { AppGlyph, StatusDot, appState } from './parts';
import type { HomeApp } from './types';

export interface DockProps {
  apps: HomeApp[];
  layout: HomeLayout;
  editing: boolean;
  hubLive: boolean;
  hrefFor: (app: HomeApp) => string;
  appsHref: string;
  onChange: (next: HomeLayout, announce: string) => void;
}

export function Dock({ apps, layout, editing, hubLive, hrefFor, appsHref, onChange }: DockProps) {
  if (!apps.length && !editing) return null;
  return (
    <nav className="omh-dock" aria-label="Dock">
      {apps.length === 0 ? (
        <p className="omh-dock-hint">Pin apps from “Your apps” to keep them here.</p>
      ) : (
        <ul>
          {apps.map((a, i) => {
            const st = appState(a, hubLive);
            return (
              <li key={a.id} className="omh-dock-item">
                <a href={hrefFor(a)} className="omh-dock-app" aria-label={`${a.name}, ${st.label}`}>
                  <AppGlyph app={a} size={44} />
                  <StatusDot tone={st.tone} hollow={st.lastKnown} className="omh-dock-dot" />
                  <span className="omh-dock-label" aria-hidden="true">
                    {a.name}
                  </span>
                </a>
                {editing && (
                  <span className="omh-dock-move">
                    <button type="button" className="omh-ibtn" aria-label={`Move ${a.name} left in the dock`} disabled={i === 0} onClick={() => onChange(movePin(layout, a.id, i - 1), `${a.name} moved to dock position ${i}.`)}>
                      <Icon name="chevron" size={14} className="omh-flip" />
                    </button>
                    <button type="button" className="omh-ibtn" aria-label={`Move ${a.name} right in the dock`} disabled={i === apps.length - 1} onClick={() => onChange(movePin(layout, a.id, i + 1), `${a.name} moved to dock position ${i + 2}.`)}>
                      <Icon name="chevron" size={14} />
                    </button>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <span className="omh-dock-sep" aria-hidden="true" />
      <a href={appsHref} className="omh-dock-app omh-dock-all">
        <span className="omh-glyph omh-glyph-add" style={{ width: 44, height: 44 }} aria-hidden="true">
          <Icon name="apps" size={20} />
        </span>
        <span className="omh-dock-label">All apps</span>
      </a>
    </nav>
  );
}
