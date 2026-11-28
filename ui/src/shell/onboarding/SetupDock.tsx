// SPDX-License-Identifier: Apache-2.0
// The desktop assembles itself (the assemble concept, founder pick 2026-11-28): from the apps step on,
// a small copy of the Atlas dock sits under the setup map, and each app the owner ticks drops into it
// with a "waiting" badge, because a ticked app is only an install request until it is approved.
// Unticking takes it out again. Drawn from props first, then animated (enter 240 ms, 50 ms stagger, at
// most 6), opacity only with reduced motion; Escape finishes it. Screen readers get one sentence.
import { useEffect, useRef } from 'react';
import { animate, useReducedMotion } from '../../motion';
import { ShellIcon, type ShellIconName } from '../icons';

/** The Atlas dock's built-in items, in dock order (dashboard screens: Home, Map, Approvals, Files, Market). */
const BUILT_IN: Array<{ id: string; label: string; icon: ShellIconName }> = [
  { id: 'home', label: 'Home', icon: 'home' },
  { id: 'map', label: 'Map', icon: 'globe' },
  { id: 'approvals', label: 'Approvals', icon: 'approvals' },
  { id: 'files', label: 'Files', icon: 'folder' },
  { id: 'market', label: 'Market', icon: 'apps' },
];

export interface DockApp { id: string; name: string; category: string }

export function SetupDock({ apps }: { apps: DockApp[] }) {
  const reduced = useReducedMotion();
  const dock = useRef<HTMLDivElement>(null);
  const seen = useRef(new Set(apps.map((a) => a.id)));

  // Keyed on the ticked IDs, not the array, so an unrelated re-render never cancels a tile mid-drop.
  const key = apps.map((a) => a.id).join('\n');
  useEffect(() => {
    const root = dock.current;
    if (!root) return;
    const ids = key ? key.split('\n') : [];
    const fresh = ids.filter((id) => !seen.current.has(id)).slice(-6);
    seen.current = new Set(ids);
    const run = fresh.map((id, i) => {
      const tile = root.querySelector(`[data-dock-app="${CSS.escape(id)}"]`);
      return tile && animate(tile, [{ opacity: 0, transform: 'translateY(-12px)' }, { opacity: 1, transform: 'none' }],
        { duration: 240, delay: i * 50, easing: 'cubic-bezier(.2,0,0,1)', fill: 'backwards' }, reduced);
    });
    return () => run.forEach((r) => r?.cancel());
  }, [key, reduced]);

  const said = apps.length
    ? `Your dock: ${BUILT_IN.map((b) => b.label).join(', ')}, then ${apps.map((a) => a.name).join(', ')}, each waiting for your approval.`
    : `Your dock: ${BUILT_IN.map((b) => b.label).join(', ')}. Apps you tick join it, waiting for your approval.`;

  return (
    <div className="oms-setup-dock">
      <p className="om-visually-hidden">{said}</p>
      <div ref={dock} className="oms-setup-dock-bar" aria-hidden="true">
        {BUILT_IN.map((b) => (
          <span key={b.id} className="oms-setup-dock-item" title={b.label}><ShellIcon name={b.icon} size={16} /></span>
        ))}
        {apps.length > 0 && <span className="oms-setup-dock-sep" />}
        {apps.map((a) => (
          <span key={a.id} className="oms-setup-dock-app" data-dock-app={a.id} title={`${a.name}, waiting`}>
            {/* The starter app's glyph classes (Onboarding AppGlyph), without its category badge at this size. */}
            <span className={`oms-glyph oms-glyph-${a.category}`} style={{ width: 26, height: 26, fontSize: 11 }}>{a.name[0]}</span>
            <span className="oms-setup-dock-wait"><ShellIcon name="clock" size={10} /></span>
          </span>
        ))}
      </div>
    </div>
  );
}
