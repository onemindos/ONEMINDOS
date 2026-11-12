// SPDX-License-Identifier: Apache-2.0
// Command palette (UX-P3): Cmd/Ctrl-K opens it anywhere. Keyboard first, WAI-ARIA combobox
// with a grouped listbox. Requests are labelled as requests and go to Approvals (P1); each
// option shows the equivalent API/CLI call (P4). Honest: results built from stale data say so.
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { cx } from '../lib/cx';
import { StatusPill } from '../components/StatusPill';
import { ShellIcon } from './icons';
import { flatten, isPaletteHotkey, moveActive, parseQuery, searchCommands, type PaletteCommand } from './palette';
import { StateView } from './StateView';
import type { ViewState } from './states';
import './shell.css';

/** Opens the palette on Cmd-K / Ctrl-K, anywhere in the page. */
export function usePaletteHotkey(onOpen: () => void): void {
  const ref = useRef(onOpen);
  ref.current = onOpen;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isPaletteHotkey(e)) {
        e.preventDefault();
        ref.current();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}

/** "⌘K" on Apple platforms, "Ctrl K" elsewhere. */
export function hotkeyLabel(platform = typeof navigator === 'undefined' ? '' : navigator.platform): string {
  return /mac|iphone|ipad/i.test(platform) ? '⌘K' : 'Ctrl K';
}

/** The search button for the top bar; shows the shortcut. */
export function PaletteTrigger({ onOpen, label = 'Search or run a command' }: { onOpen: () => void; label?: string }) {
  return (
    <button type="button" className="oms-trigger" onClick={onOpen} aria-keyshortcuts="Meta+K Control+K">
      <ShellIcon name="search" size={18} />
      <span className="oms-trigger-text">{label}</span>
      <kbd className="oms-kbd">{hotkeyLabel()}</kbd>
    </button>
  );
}

const SCOPES: Array<{ prefix: string; label: string }> = [
  { prefix: '', label: 'All' },
  { prefix: '> ', label: 'Requests' },
  { prefix: '@', label: 'Nodes' },
  { prefix: '#', label: 'Categories' },
];

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  commands: PaletteCommand[];
  /** Called with the chosen command; navigation or request creation is the caller's job. */
  onRun: (cmd: PaletteCommand) => void;
  recent?: string[];
  /** Data state of the command source: loading, error, stale or offline are shown honestly. */
  state?: ViewState;
  /** Seconds since the data was confirmed, for stale/offline. */
  ageSeconds?: number;
  initialQuery?: string;
}

function Highlight({ text, query }: { text: string; query: string }): ReactNode {
  const t = parseQuery(query).text.trim();
  if (!t) return text;
  const i = text.toLowerCase().indexOf(t.toLowerCase());
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <mark className="oms-mark">{text.slice(i, i + t.length)}</mark>
      {text.slice(i + t.length)}
    </>
  );
}

export function CommandPalette({ open, onClose, commands, onRun, recent, state = 'ready', ageSeconds, initialQuery = '' }: CommandPaletteProps) {
  const [query, setQuery] = useState(initialQuery);
  const [active, setActive] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const listId = useId();
  const hintId = useId();
  const optId = (i: number) => `${listId}-o${i}`;

  const groups = useMemo(() => searchCommands(commands, query, { recent }), [commands, query, recent]);
  const flat = useMemo(() => flatten(groups), [groups]);
  const current = flat[active];

  useEffect(() => setActive(0), [query]);
  useEffect(() => setNotice(null), [active, query]);

  useEffect(() => {
    if (!open) return;
    setQuery(initialQuery);
    const opener = document.activeElement as HTMLElement | null;
    input.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
      opener?.focus?.();
    };
  }, [open, initialQuery]);

  useEffect(() => {
    document.getElementById(optId(active))?.scrollIntoView?.({ block: 'nearest' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  if (!open) return null;

  const run = (cmd: PaletteCommand | undefined) => {
    if (!cmd) return;
    if (cmd.disabledReason && !cmd.href) {
      setNotice(cmd.disabledReason);
      return;
    }
    onRun(cmd);
    onClose();
  };

  const onKeyDown = (e: ReactKeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      if (query) setQuery('');
      else onClose();
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || ((e.key === 'Home' || e.key === 'End') && e.ctrlKey)) {
      e.preventDefault();
      setActive((a) => moveActive(a, e.key, flat.length));
      return;
    }
    if (e.key === 'Enter' && e.target === input.current) {
      e.preventDefault();
      run(current);
      return;
    }
    if (e.key === 'Tab') {
      // keep focus inside the dialog
      const items = Array.from(panel.current?.querySelectorAll<HTMLElement>('input, button:not([disabled])') ?? []);
      if (items.length === 0) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };

  const scope = parseQuery(query).scope;
  const scopeIndex = { all: 0, requests: 1, nodes: 2, category: 3 }[scope];
  let index = -1;

  const body = (() => {
    if (state === 'loading' || state === 'error' || state === 'forbidden') {
      return (
        <div className="oms-palette-state">
          <StateView state={state} compact what="Loading apps and nodes" error={{ error: 'unreachable', message: 'The hub did not answer. Navigation still works.' }} />
        </div>
      );
    }
    if (flat.length === 0) {
      return (
        <div className="oms-palette-state">
          <StateView state="empty" compact empty={{ icon: 'search', title: query ? `No matches for “${parseQuery(query).text}”` : 'Nothing here yet', body: 'Try a shorter word, a category such as “media”, or type > to see requests you can make.' }} />
        </div>
      );
    }
    return (
      <div role="listbox" id={listId} aria-label="Results" className="oms-palette-list">
        {groups.map((g) => (
          <div role="group" key={g.group} aria-labelledby={`${listId}-${g.group}`} className="oms-palette-group">
            <div role="presentation" id={`${listId}-${g.group}`} className="oms-palette-group-title">
              {g.group}
            </div>
            {g.items.map((c) => {
              index += 1;
              const i = index;
              const on = i === active;
              return (
                <div
                  role="option"
                  id={optId(i)}
                  key={`${g.group}-${c.id}`}
                  aria-selected={on}
                  aria-disabled={c.disabledReason && !c.href ? true : undefined}
                  className={cx('oms-option', on && 'oms-option-on', c.disabledReason && 'oms-option-muted')}
                  onMouseMove={() => active !== i && setActive(i)}
                  onClick={() => run(c)}
                >
                  <span className={cx('oms-option-icon', c.request && 'oms-option-icon-req')}>
                    <ShellIcon name={c.icon} size={18} />
                  </span>
                  <span className="oms-option-text">
                    <span className="oms-option-title">
                      <Highlight text={c.title} query={query} />
                    </span>
                    {(c.subtitle || c.disabledReason) && <span className="oms-option-sub">{c.disabledReason && !c.href ? c.disabledReason : c.subtitle}</span>}
                  </span>
                  {c.request && <span className="oms-req-tag">Request</span>}
                  {c.pill && <StatusPill tone={c.pill.tone} label={c.pill.label} className="oms-option-pill" />}
                  <span className="oms-option-enter" aria-hidden="true">
                    <ShellIcon name="enter" size={16} />
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    );
  })();

  return createPortal(
    <div className="oms-palette-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={panel} className="oms-palette" role="dialog" aria-modal="true" aria-label="Command palette" onKeyDown={onKeyDown}>
        <div className="oms-palette-search">
          <ShellIcon name="search" size={20} />
          <input
            ref={input}
            className="oms-palette-input"
            type="text"
            role="combobox"
            aria-expanded={flat.length > 0}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={current ? optId(active) : undefined}
            aria-describedby={hintId}
            aria-label="Search apps, nodes, settings and requests"
            placeholder="Search, or type > to make a request"
            value={query}
            spellCheck={false}
            autoComplete="off"
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="button" className="oms-kbd oms-kbd-btn" onClick={onClose} aria-label="Close">
            esc
          </button>
        </div>
        <div className="oms-scopes" role="toolbar" aria-label="Search in">
          {SCOPES.map((s, i) => (
            <button
              key={s.label}
              type="button"
              className="oms-scope"
              aria-pressed={i === scopeIndex}
              onClick={() => {
                setQuery(s.prefix + parseQuery(query).text);
                input.current?.focus();
              }}
            >
              {s.label}
              {s.prefix && <kbd className="oms-scope-key">{s.prefix.trim()}</kbd>}
            </button>
          ))}
        </div>
        {(state === 'stale' || state === 'offline') && (
          <p className={cx('oms-palette-note', state === 'offline' ? 'om-tone-neutral' : 'om-tone-warn')} role="status">
            <ShellIcon name={state === 'offline' ? 'offline' : 'clock'} size={16} />
            {state === 'offline' ? 'Hub offline: ' : 'Not live: '}
            statuses below are from the last report{ageSeconds !== undefined ? ` ${Math.round(ageSeconds / 60)} min ago` : ''}. Requests will wait until the hub answers.
          </p>
        )}
        {body}
        <div className="oms-palette-foot" id={hintId}>
          {notice ? (
            <span className="oms-foot-notice" role="status">
              <ShellIcon name="lock" size={14} /> {notice}
            </span>
          ) : current?.equivalent ? (
            <span className="oms-foot-eq">
              <span className="oms-foot-eq-label">Same as</span> <code>{current.equivalent}</code>
            </span>
          ) : (
            <span className="oms-foot-eq">{current?.request ? 'Creates a request that waits for approval' : ' '}</span>
          )}
          <span className="oms-foot-keys" aria-hidden="true">
            <kbd className="oms-kbd">↑</kbd>
            <kbd className="oms-kbd">↓</kbd> move <kbd className="oms-kbd">↵</kbd> {current?.request ? 'request' : 'open'} <kbd className="oms-kbd">esc</kbd> close
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
