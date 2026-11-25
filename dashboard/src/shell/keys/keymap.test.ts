// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { createElement } from 'react';
import { expect, it, vi } from 'vitest';
import { BROWSER_RESERVED, KEYMAP, bindingId, entryFor, matches } from './keymap';
import { ShortcutSheet } from './ShortcutSheet';
import { useKeymap, type KeyHandlers } from './useKeymap';

const event = (init: Partial<KeyboardEvent>) => ({ key: '', code: '', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...init });
function Probe({ handlers }: { handlers: KeyHandlers }) {
  useKeymap(handlers);
  return createElement('div', null, createElement('input', { 'aria-label': 'Field' }), createElement('div', { contentEditable: true, role: 'textbox', 'aria-label': 'Note' }));
}

it('lists each entry once: no two entries share a binding', () => {
  expect(new Set(KEYMAP.map(e => e.id)).size).toBe(KEYMAP.length);
  const bound = KEYMAP.flatMap(e => e.bindings.map(bindingId));
  expect(bound.filter((id, i) => bound.indexOf(id) !== i)).toEqual([]);
});

it('never takes a key the browser reserves', () => {
  const taken = new Set(KEYMAP.flatMap(e => e.bindings.map(bindingId)));
  expect(BROWSER_RESERVED.map(bindingId).filter(id => taken.has(id))).toEqual([]);
  for (const key of ['w', 't', 'n', 'l', 'Tab']) {
    expect(entryFor(event({ key, ctrlKey: true }))).toBeUndefined();
    expect(entryFor(event({ key, metaKey: true }))).toBeUndefined();
  }
});

it('matches Ctrl or ⌘ K, Alt digits by physical key, and ? without Ctrl, ⌘ or Alt', () => {
  expect(entryFor(event({ key: 'k', ctrlKey: true }))?.id).toBe('palette');
  expect(entryFor(event({ key: 'K', metaKey: true }))?.id).toBe('palette');
  expect(entryFor(event({ key: '¡', code: 'Digit1', altKey: true }))?.id).toBe('workspace-1');
  expect(entryFor(event({ key: '⁄', code: 'Digit4', altKey: true, shiftKey: true }))?.id).toBe('send-4');
  expect(entryFor(event({ key: '?', shiftKey: true }))?.id).toBe('shortcuts');
  expect(entryFor(event({ key: '?', ctrlKey: true }))).toBeUndefined();
  expect(entryFor(event({ key: 'k' }))).toBeUndefined();
  expect(matches(KEYMAP.find(e => e.id === 'close')!, event({ key: 'Escape' }))).toBe(true);
});

it('refuses a handler for a shortcut that is not in the keymap', () => {
  const quiet = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  expect(() => render(createElement(Probe, { handlers: { 'steal-ctrl-w': () => undefined } }))).toThrow(/not in the keymap/);
  quiet.mockRestore();
});

it('runs a handler for its key and ignores the key while typing in a field or editable element', async () => {
  const user = userEvent.setup();
  const palette = vi.fn();
  render(createElement(Probe, { handlers: { palette, 'workspace-2': palette } }));
  await user.keyboard('{Control>}k{/Control}');
  expect(palette).toHaveBeenCalledTimes(1);
  await user.click(screen.getByLabelText('Field'));
  await user.keyboard('{Control>}k{/Control}');
  await user.click(screen.getByRole('textbox', { name: 'Note' }));
  await user.keyboard('{Control>}k{/Control}');
  expect(palette).toHaveBeenCalledTimes(1);
});

it('lists every keymap entry in the shortcuts sheet, which has no accessibility violations', async () => {
  const { baseElement } = render(createElement(ShortcutSheet, { open: true, onClose: () => undefined }));
  const sheet = screen.getByRole('dialog', { name: 'Keyboard shortcuts' });
  for (const entry of KEYMAP) {
    const row = within(sheet).getByText(entry.description).closest('div')!;
    expect(within(row as HTMLElement).getByText(entry.keys)).toBeInTheDocument();
  }
  const result = await axe.run(baseElement, { rules: { 'color-contrast': { enabled: false } } });
  expect(result.violations.map(v => v.id)).toEqual([]);
});

it('binds no shortcut outside the keymap: no hotkey code beside it in the shell', () => {
  const sources = import.meta.glob(['../**/*.{ts,tsx}', '!../**/*.test.*', '!../keys/**'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
  expect(Object.keys(sources).length).toBeGreaterThan(5);
  const offenders = Object.entries(sources).filter(([, code]) => /usePaletteHotkey|(ctrlKey|metaKey)\)?\s*&&|\.key === '(?!Escape|Tab)[^']+'/.test(code)).map(([file]) => file);
  expect(offenders).toEqual([]);
});
