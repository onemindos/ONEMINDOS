// SPDX-License-Identifier: Apache-2.0
// The launcher (final design 03): the OneMind logo tile in the dock, or Ctrl/⌘ + /. One search across your apps,
// the system screens, machines and commands, with a best match (Enter opens it). Every command shows its exact
// `onemind` line, with a copy button; a command that changes something is marked "asks a person" and only files a
// request that waits in Approvals (D-027). Moved out of DesktopShell.tsx first (DESIGN-GAP lane A1), grown here (B).
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { AppIcon, Icon, type NavItem, type PaletteCommand } from '@onemind/ui';
import type { DockApp } from './DesktopShell';
import { MACHINE_WORD, SCOPE_LABEL, asksAPerson, commandLine, launcherItems, searchLauncher, type LauncherItem, type LauncherMachine, type LauncherScope } from './launcher';
import { overlayOpen } from './overlay';
import { Badge, ScreenTile } from './tiles';

export interface LaunchpadProps {
  nav: NavItem[];
  apps: DockApp[];
  /** Machines from GET /v1/nodes, aged on the hub clock. Empty when this person cannot see Nodes. */
  machines?: LauncherMachine[];
  /** The palette's commands (built from the hub's apps, nodes and requests). */
  commands?: PaletteCommand[];
  /** Run a command the way the palette does: open its screen, or file its request. */
  onRun?: (c: PaletteCommand) => void;
  onClose: () => void;
  onShortcuts: () => void;
}

export function Launchpad({ nav, apps, machines = [], commands = [], onRun, onClose, onShortcuts }: LaunchpadProps) {
  const [q, setQ] = useState('');
  const [scope, setScope] = useState<LauncherScope>('all');
  const [copied, setCopied] = useState<string | null>(null);
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
      // Back to whatever opened it (the dock's logo tile), if it is still on the page.
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  const items = useMemo(() => launcherItems({ nav, apps, machines, commands: onRun ? commands : [] }), [nav, apps, machines, commands, onRun]);
  const { best, groups, counts } = searchLauncher(items, q, scope);
  const inBest = new Set(best.map((i) => i.key));
  const rest = (k: keyof typeof groups) => groups[k].filter((i) => !inBest.has(i.key));
  const run = (c: PaletteCommand) => {
    if (c.disabledReason && !c.href) return; // the reason is shown on the row; nothing is filed
    onClose();
    onRun?.(c);
  };
  // "Copied" is said once through a polite live region, then cleared, so the next copy is announced again.
  const [announce, setAnnounce] = useState('');
  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => {
      setCopied(null);
      setAnnounce('');
    }, 2000);
    return () => window.clearTimeout(t);
  }, [copied, announce]);
  const copy = (text: string, key: string) => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(key);
      setAnnounce(`Copied: ${text}`);
    }, () => setAnnounce('Could not copy: the browser refused the clipboard.'));
  };
  const openBest = () => ref.current?.querySelector<HTMLElement>('[data-best="0"]')?.click();
  const nothing = best.length === 0 && Object.values(groups).every((g) => g.length === 0);

  const tile = (i: LauncherItem, index?: number) => {
    if (i.command) return null;
    return (
      <li key={i.key}>
        <a href={i.href} className="dsk-launchpad-item" data-best={index === undefined ? undefined : String(index)} onClick={onClose}>
          {i.app ? <AppIcon app={i.app} size={i.kind === 'apps' && index === undefined ? 84 : 56} /> : i.nav ? <ScreenTile id={i.nav.id} icon={i.nav.icon} size={44} /> : <span className="dsk-tile" aria-hidden="true"><Icon name="nodes" size={22} /></span>}
          <span className="dsk-launchpad-label">{i.title}</span>
          {i.machine && <small className={`dsk-launchpad-state dsk-fleet-${MACHINE_WORD[i.machine.status]}`}><span className="dsk-state-dot" aria-hidden="true" />{MACHINE_WORD[i.machine.status]}</small>}
          {i.nav && <Badge item={i.nav} />}
        </a>
      </li>
    );
  };
  const commandRow = (i: LauncherItem, index?: number) => {
    const c = i.command!;
    const line = commandLine(c);
    return (
      <li key={i.key} className="dsk-cmd">
        <button type="button" className="dsk-cmd-run" data-best={index === undefined ? undefined : String(index)} onClick={() => run(c)} aria-disabled={c.disabledReason && !c.href ? true : undefined}>
          <span className="dsk-cmd-title">{c.title}</span>
          {asksAPerson(c) && <span className="dsk-cmd-asks">asks a person</span>}
          {c.disabledReason && !c.href && <span className="dsk-cmd-why">{c.disabledReason}</span>}
        </button>
        {line && (
          <span className="dsk-cmd-line">
            <code>{line.text}</code>
            <button type="button" className="dsk-cmd-copy" onClick={() => copy(line.cli ? line.text.slice(2) : line.text, i.key)}>
              <span aria-hidden="true">{copied === i.key ? 'Copied' : 'Copy'}</span>
              <span className="om-visually-hidden">Copy {line.cli ? 'command' : 'API call'}: {line.text}</span>
            </button>
          </span>
        )}
      </li>
    );
  };
  const section = (label: string, list: LauncherItem[], big = false) =>
    list.length > 0 && (
      <section aria-label={label}>
        <h3 className="dsk-launchpad-head">{label}</h3>
        <ul className={`dsk-launchpad-grid ${big ? 'dsk-launchpad-big' : 'dsk-launchpad-small'}`}>{list.map((i) => tile(i))}</ul>
      </section>
    );
  const pills: LauncherScope[] = ['all', ...(['apps', 'system', 'machines', 'commands'] as const).filter((k) => counts[k] > 0)];
  return (
    <div className="dsk-launchpad" role="dialog" aria-modal="true" aria-labelledby={title} ref={ref} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dsk-launchpad-inner">
        <h2 id={title} className="om-visually-hidden">
          Launcher
        </h2>
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault(); // Enter opens the best match
            openBest();
          }}
        >
          <label className="dsk-launchpad-search">
            <Icon name="search" size={18} />
            <span className="om-visually-hidden">Find an app, screen, machine or command</span>
            <input ref={input} type="search" placeholder="Find an app, screen, machine or command" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </form>
        <div className="dsk-launchpad-pills" role="group" aria-label="Show">
          {pills.map((k) => (
            <button key={k} type="button" className="dsk-pill" aria-pressed={scope === k} onClick={() => setScope(k)}>
              {SCOPE_LABEL[k]}
              {k !== 'all' && <span className="dsk-pill-count">{counts[k]}</span>}
            </button>
          ))}
        </div>
        {best.length > 0 && (
          <section aria-label="Best match">
            <h3 className="dsk-launchpad-head">Best match <span className="dsk-launchpad-dim">· Enter opens the first</span></h3>
            <ul className="dsk-launchpad-grid dsk-launchpad-small">{best.filter((i) => !i.command).map((i) => tile(i, best.indexOf(i)))}</ul>
            {best.some((i) => i.command) && <ul className="dsk-cmds">{best.filter((i) => i.command).map((i) => commandRow(i, best.indexOf(i)))}</ul>}
          </section>
        )}
        {section('Your apps', rest('apps'), true)}
        {section('System', rest('system'))}
        {section('Machines', rest('machines'))}
        {rest('commands').length > 0 && (
          <section aria-label="Commands">
            <h3 className="dsk-launchpad-head">Commands <span className="dsk-launchpad-dim">· each shows the exact onemind command; anything that changes the box goes to Approvals</span></h3>
            <ul className="dsk-cmds">{rest('commands').slice(0, q.trim() ? 8 : 6).map((i) => commandRow(i))}</ul>
          </section>
        )}
        <p className="om-visually-hidden" role="status" aria-live="polite">
          {announce}
        </p>
        <button type="button" className="dsk-launchpad-keys" onClick={onShortcuts}>
          <Icon name="settings" size={16} /> Keyboard shortcuts
        </button>
        {nothing && <p className="dsk-launchpad-none">Nothing matches “{q}”. Try the search (Ctrl K) for settings and actions.</p>}
      </div>
    </div>
  );
}
