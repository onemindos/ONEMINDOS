// SPDX-License-Identifier: Apache-2.0
// Whether something else owns Esc right now. Shared by the desktop frame and the launcher.

/**
 * Esc belongs to something else: a modal dialog or the palette, or a popover opened from the
 * menu bar (the bell, the account menu: their triggers say aria-expanded). Expandable sections
 * inside a page do not count.
 */
export function overlayOpen(except?: Element | null): boolean {
  return [...document.querySelectorAll('[aria-modal="true"], dialog[open], .dsk-bar [aria-expanded="true"]')].some((e) => e !== except);
}

