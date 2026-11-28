// SPDX-License-Identifier: Apache-2.0
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { HoldToApprove } from './HoldToApprove';

beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] }));
afterEach(() => { cleanup(); vi.useRealTimers(); });
const advance = (ms: number) => act(() => vi.advanceTimersByTime(ms));

function show() {
  const approve = vi.fn();
  render(<HoldToApprove label="Hold to approve the request" onApprove={approve} />);
  return { approve, hold: screen.getByRole('button', { name: 'Hold to approve the request' }) };
}

it('completes a pointer hold at 2000 ms with unchanged label layout', () => {
  const { hold, approve } = show();
  const label = hold.querySelector('.om-hold-label');
  fireEvent(hold, new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
  advance(1999);
  expect(approve).not.toHaveBeenCalled();
  expect(hold.querySelector('.om-hold-label')).toBe(label);
  expect(label).not.toHaveAttribute('style');
  advance(1);
  expect(approve).toHaveBeenCalledExactlyOnceWith(2000);
});

it('cancels a 1000 ms release and a later Escape', () => {
  const { hold, approve } = show();
  fireEvent.keyDown(hold, { key: ' ' });
  advance(1000);
  fireEvent.keyUp(hold, { key: ' ' });
  advance(1000);
  fireEvent.keyDown(hold, { key: ' ' });
  fireEvent.keyDown(hold, { key: 'Escape' });
  advance(2000);
  fireEvent.keyUp(hold, { key: ' ' });
  expect(approve).not.toHaveBeenCalled();
});

it('consumes Enter repeat and completes only on keyup', () => {
  const { hold, approve } = show();
  hold.focus();
  fireEvent.keyDown(hold, { key: 'Enter' });
  advance(2000);
  expect(document.activeElement).toBe(hold);
  expect(approve).not.toHaveBeenCalled();
  expect(fireEvent.keyDown(hold, { key: 'Enter', repeat: true })).toBe(false);
  fireEvent.keyUp(hold, { key: 'Enter' });
  expect(approve).toHaveBeenCalledExactlyOnceWith(2000);
});

it('offers a separate confirm action after the same elapsed time', () => {
  const { approve } = show();
  fireEvent.click(screen.getByRole('button', { name: 'Use confirmation instead' }));
  const confirm = screen.getByRole('button', { name: 'Confirm approval' });
  expect(confirm).toBeDisabled();
  advance(2000);
  expect(confirm).toBeEnabled();
  expect(approve).not.toHaveBeenCalled();
  fireEvent.click(confirm);
  expect(approve).toHaveBeenCalledExactlyOnceWith(2000);
});
