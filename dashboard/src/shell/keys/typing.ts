// SPDX-License-Identifier: Apache-2.0
/** True while the key goes to a text field or an editable element: shortcuts must leave it alone. */
export function typingIn(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || !!target.closest('[contenteditable]:not([contenteditable="false"])') || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
}
