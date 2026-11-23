// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from 'react';
import { KEYMAP, entryFor } from './keymap';
import { typingIn } from './typing';

export type KeyHandlers = Record<string, (e: KeyboardEvent) => void | false>;

/**
 * Bind handlers to entries of the keymap, by id. An id missing from the table throws, so a
 * shortcut cannot exist without being listed. Nothing fires while a person is typing, after
 * another handler took the key, or during text composition.
 */
export function useKeymap(handlers: KeyHandlers): void {
  for (const id of Object.keys(handlers)) {
    if (!KEYMAP.some(entry => entry.id === id)) throw new Error(`Shortcut "${id}" is not in the keymap (shell/keys/keymap.ts)`);
  }
  const latest = useRef(handlers);
  latest.current = handlers;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.isComposing || typingIn(e.target)) return;
      const entry = entryFor(e);
      const handler = entry && latest.current[entry.id];
      if (!handler) return;
      // A handler that returns false declines the key, which then keeps its normal meaning.
      if (handler(e) !== false) e.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}
