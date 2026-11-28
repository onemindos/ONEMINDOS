// SPDX-License-Identifier: Apache-2.0
// The one table of keyboard shortcuts, and the only place a shortcut is bound. `useKeymap` reads
// it, the "Keyboard shortcuts" sheet lists it, and keymap.test.ts fails on a collision, on a key
// the browser reserves, or on a handler for an id that is not here.
import { WORKSPACES } from '../wm/store';

/** `cmd` is Ctrl on Windows and Linux, ⌘ on a Mac. `none` still allows Shift (for "?"). */
export type Mod = 'cmd' | 'alt' | 'altshift' | 'none';
/** `code` is the physical key (stable under Alt and Shift on any layout); `key` is the typed character. */
export interface Binding { mod: Mod; key?: string; code?: string }
export type Group = 'Open' | 'Windows' | 'Workspaces' | 'Tiling' | 'Help';
export interface KeyEntry { id: string; group: Group; description: string; keys: string; bindings: Binding[] }

const digits = Array.from({ length: WORKSPACES }, (_, i) => i + 1);
export const KEYMAP: readonly KeyEntry[] = [
  { id: 'palette', group: 'Open', description: 'Search and run commands', keys: 'Ctrl/⌘ K', bindings: [{ mod: 'cmd', key: 'k' }] },
  { id: 'launchpad', group: 'Open', description: 'Launcher: every screen, app, machine and command', keys: 'Ctrl/⌘ /', bindings: [{ mod: 'cmd', key: '/' }] },
  // The design says Alt Space, but Windows and most Linux desktops keep Alt Space for the window menu and macOS types a
  // non-breaking space with it, so the page never sees it reliably. Alt R ("run") is free in every browser we support.
  { id: 'run-bar', group: 'Open', description: 'Run bar in the dock (when switched on in Appearance)', keys: 'Alt R', bindings: [{ mod: 'alt', code: 'KeyR' }] },
  { id: 'close', group: 'Windows', description: 'Close the open window (back to the desktop)', keys: 'Esc', bindings: [{ mod: 'none', key: 'Escape' }] },
  { id: 'cycle-next', group: 'Windows', description: 'Next window on this workspace', keys: 'Alt ]', bindings: [{ mod: 'alt', code: 'BracketRight' }] },
  { id: 'cycle-previous', group: 'Windows', description: 'Previous window on this workspace', keys: 'Alt [', bindings: [{ mod: 'alt', code: 'BracketLeft' }] },
  { id: 'snap-left', group: 'Windows', description: 'Snap the window to the left half', keys: 'Alt Shift ←', bindings: [{ mod: 'altshift', code: 'ArrowLeft' }] },
  { id: 'snap-right', group: 'Windows', description: 'Snap the window to the right half', keys: 'Alt Shift →', bindings: [{ mod: 'altshift', code: 'ArrowRight' }] },
  ...digits.map((n): KeyEntry => ({ id: `workspace-${n}`, group: 'Workspaces', description: `Go to workspace ${n}`, keys: `Alt ${n}`, bindings: [{ mod: 'alt', code: `Digit${n}` }] })),
  ...digits.map((n): KeyEntry => ({ id: `send-${n}`, group: 'Workspaces', description: `Send the window to workspace ${n}`, keys: `Alt Shift ${n}`, bindings: [{ mod: 'altshift', code: `Digit${n}` }] })),
  { id: 'tiling', group: 'Tiling', description: 'Turn tiling on or off', keys: 'Alt T', bindings: [{ mod: 'alt', code: 'KeyT' }] },
  { id: 'tips-search', group: 'Help', description: 'Focus search in Tips', keys: '/', bindings: [{ mod: 'none', key: '/' }] },
  { id: 'shortcuts', group: 'Help', description: 'Keyboard shortcuts (this sheet)', keys: '?', bindings: [{ mod: 'none', key: '?' }] },
];

/** Keys a browser keeps for itself: Ctrl/⌘ + W, T, N, L and Tab. */
export const BROWSER_RESERVED: readonly Binding[] = [
  ...['w', 't', 'n', 'l'].map((key): Binding => ({ mod: 'cmd', key })),
  { mod: 'cmd', key: 'Tab' },
];

export const bindingId = (b: Binding) => `${b.mod}+${(b.code ?? b.key ?? '').toLowerCase()}`;

type KeyLike = Pick<KeyboardEvent, 'key' | 'code' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'>;
function modOk(mod: Mod, e: KeyLike): boolean {
  const cmd = e.ctrlKey || e.metaKey;
  if (mod === 'cmd') return cmd && !e.altKey && !e.shiftKey;
  if (mod === 'alt') return e.altKey && !cmd && !e.shiftKey;
  if (mod === 'altshift') return e.altKey && e.shiftKey && !cmd;
  return !cmd && !e.altKey;
}
export function matches(entry: KeyEntry, e: KeyLike): boolean {
  return entry.bindings.some(b => modOk(b.mod, e) && (b.code ? e.code === b.code : e.key.toLowerCase() === b.key?.toLowerCase()));
}
export function entryFor(e: KeyLike): KeyEntry | undefined {
  return KEYMAP.find(entry => matches(entry, e));
}
