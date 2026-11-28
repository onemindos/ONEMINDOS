// SPDX-License-Identifier: Apache-2.0
// Launchpad: every screen and app with a search field (the grid button in the dock, or Ctrl/⌘ + /).
// Moved out of DesktopShell.tsx so the launcher can grow on its own (DESIGN-GAP lane A1/B).
import { useEffect, useId, useRef, useState } from 'react';
import { AppIcon, Icon, type NavItem } from '@onemind/ui';
import type { DockApp } from './DesktopShell';
import { overlayOpen } from './overlay';
import { Badge, ScreenTile } from './tiles';

export function Launchpad({ nav, apps, onClose, onShortcuts }: { nav: NavItem[]; apps: DockApp[]; onClose: () => void; onShortcuts: () => void }) {
  const [q, setQ] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const title = useId();
  const input = useRef<HTMLInputElement>(null);
  // The latest onClose without re-running the effect: the shell re-renders on every hub poll,
  // and re-running would pull focus back to the search field each time.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !overlayOpen(ref.current)) {
        e.preventDefault();
        closeRef.current();
        return;
      }
      // Keep Tab inside Launchpad while it is open (aria-modal).
      if (e.key === 'Tab' && ref.current) {
        const items = [...ref.current.querySelectorAll<HTMLElement>('a[href], button, input, [tabindex]:not([tabindex="-1"])')];
        const first = items[0];
        const last = items[items.length - 1];
        if (!first || !last) return;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      // Back to whatever opened it (the dock's All button), if it is still on the page.
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  const needle = q.trim().toLowerCase();
  const screens = nav.filter((n) => !needle || n.label.toLowerCase().includes(needle));
  const shownApps = apps.filter((a) => !needle || a.name.toLowerCase().includes(needle));
  return (
    <div className="dsk-launchpad" role="dialog" aria-modal="true" aria-labelledby={title} ref={ref} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dsk-launchpad-inner">
        <h2 id={title} className="om-visually-hidden">
          Launchpad
        </h2>
        <label className="dsk-launchpad-search">
          <Icon name="search" size={18} />
          <span className="om-visually-hidden">Find a screen or app</span>
          <input ref={input} type="search" placeholder="Find a screen or app" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        {shownApps.length > 0 && (
          <section aria-label="Your apps">
            <h3 className="dsk-launchpad-head">Your apps</h3>
            <ul className="dsk-launchpad-grid dsk-launchpad-big">
              {shownApps.map((a) => (
                <li key={a.id}>
                  <a href={a.href} className="dsk-launchpad-item" onClick={onClose}>
                    <AppIcon app={a} size={84} />
                    <span className="dsk-launchpad-label">{a.name}</span>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}
        <section aria-label="Screens">
          <h3 className="dsk-launchpad-head">Screens</h3>
          <ul className="dsk-launchpad-grid dsk-launchpad-small">
            {screens.map((n) => (
              <li key={n.id}>
                <a href={n.href} className="dsk-launchpad-item" onClick={onClose}>
                  <ScreenTile id={n.id} icon={n.icon} size={44} />
                  <span className="dsk-launchpad-label">{n.label}</span>
                  <Badge item={n} />
                </a>
              </li>
            ))}
          </ul>
        </section>
        <button type="button" className="dsk-launchpad-keys" onClick={onShortcuts}>
          <Icon name="settings" size={16} /> Keyboard shortcuts
        </button>
        {screens.length === 0 && shownApps.length === 0 && <p className="dsk-launchpad-none">Nothing matches “{q}”. Try the search (Ctrl K) for settings and actions.</p>}
      </div>
    </div>
  );
}

