// SPDX-License-Identifier: Apache-2.0
// The run bar (final design 09, the Console graft the founder asked for): "run a command or ask an agent", in the
// dock, Alt R (the design's Alt Space is the window menu on Windows and Linux: keys/keymap.ts). Off by default
// (Settings > Appearance). Typed text resolves to the best palette command: a screen
// opens; a change (restart nextcloud) goes through the same reviewed request as the palette (the plan preview, then
// one POST /v1/actions) and never acts. When the same request already waits in Approvals, the bar opens that one
// instead of filing a second. A free-text question would go to an agent, but no Ask route exists yet: it says so.
import { forwardRef, useState } from 'react';
import { Icon, scorePaletteCommand, type PaletteCommand } from '@onemind/ui';

/** A request already waiting for a decision: its type and app. */
export interface WaitingRequest {
  id: string;
  type: string;
  appId?: string;
}

export type RunResolution =
  | { kind: 'existing'; href: string; command: PaletteCommand }
  | { kind: 'run'; command: PaletteCommand }
  | { kind: 'none' };

/** Minimum score for a typed line to count as a command (every word must match; this drops one-letter noise). */
const MIN_SCORE = 40;

export function resolveRun(text: string, commands: readonly PaletteCommand[], waiting: readonly WaitingRequest[]): RunResolution {
  const t = text.trim();
  if (!t) return { kind: 'none' };
  const ranked = commands
    .filter((c) => c.group !== 'Approvals' && !(c.disabledReason && !c.href))
    .map((c) => ({ c, s: scorePaletteCommand(c, t) }))
    .filter((x) => x.s >= MIN_SCORE)
    .sort((a, b) => b.s - a.s);
  const top = ranked[0]?.c;
  if (!top) return { kind: 'none' };
  if (top.request) {
    const appId = String(top.request.params.app_id ?? '');
    const same = waiting.find((w) => w.type === top.request!.type && (w.appId ?? '') === appId);
    if (same) return { kind: 'existing', href: `/approvals/${encodeURIComponent(same.id)}`, command: top };
  }
  return { kind: 'run', command: top };
}

export interface RunBarProps {
  commands: readonly PaletteCommand[];
  waiting: readonly WaitingRequest[];
  onRun: (c: PaletteCommand) => void;
  onOpen: (href: string) => void;
}

export const RunBar = forwardRef<HTMLInputElement, RunBarProps>(function RunBar({ commands, waiting, onRun, onOpen }, ref) {
  const [text, setText] = useState('');
  const [note, setNote] = useState('');
  const submit = () => {
    const r = resolveRun(text, commands, waiting);
    if (r.kind === 'none') {
      setNote(text.trim() ? `No command matches “${text.trim()}”. Asking an agent is not available on this box yet; try Search (Ctrl K).` : '');
      return;
    }
    setNote(r.kind === 'existing' ? `${r.command.title}: already waiting in Approvals, opened instead of asking twice.` : '');
    setText('');
    if (r.kind === 'existing') onOpen(r.href);
    else onRun(r.command);
  };
  return (
    <form
      className="dsk-runbar"
      role="search"
      aria-label="Run bar"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <Icon name="menu" size={16} />
      <label className="om-visually-hidden" htmlFor="dsk-runbar-input">Run a command or ask an agent</label>
      <input
        id="dsk-runbar-input"
        ref={ref}
        type="text"
        autoComplete="off"
        spellCheck={false}
        placeholder="Run a command or ask an agent"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setNote('');
        }}
        aria-describedby={note ? 'dsk-runbar-note' : undefined}
        aria-keyshortcuts="Alt+R"
      />
      <span className="dsk-runbar-keys" aria-hidden="true">
        <kbd>Alt</kbd> <kbd>R</kbd>
      </span>
      <p id="dsk-runbar-note" className="dsk-runbar-note" role="status">
        {note}
      </p>
    </form>
  );
});
