// SPDX-License-Identifier: Apache-2.0
import shellStyles from '../shell/shell.css?raw';
import { renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { animate, useReducedMotion } from './index';

function target() {
  const element = document.createElement('div');
  const finish = vi.fn();
  const start = vi.fn(() => ({ finish, finished: Promise.resolve() }));
  Object.defineProperty(element, 'animate', { value: start });
  return { element, start, finish };
}

afterEach(() => vi.unstubAllGlobals());

it('follows the system preference and substitutes only opacity without a delay', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  expect(renderHook(() => useReducedMotion()).result.current).toBe(true);
  expect(renderHook(() => useReducedMotion(false)).result.current).toBe(false);
  const { element, start } = target();
  animate(element, [{ transform: 'translateY(8px)' }, { transform: 'none' }], { duration: 240, delay: 50 });
  expect(start).toHaveBeenCalledWith([{ opacity: 0 }, { opacity: 1 }], { duration: 160, delay: 0 });
});

it('finishes presentation frames on Escape but never finishes a hold', () => {
  const presentation = target();
  const hold = target();
  animate(presentation.element, [{ opacity: 0 }, { opacity: 1 }], { duration: 140 }, false);
  animate(hold.element, [{ opacity: 0 }, { opacity: 1 }], { duration: 2000, hold: true }, false);
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
  expect(presentation.finish).toHaveBeenCalledOnce();
  expect(hold.finish).not.toHaveBeenCalled();
});

it('keeps backdrop-filter out of shell animation keyframes', () => {
  const frames = [...shellStyles.matchAll(/@keyframes\s+[^\s]+\s*\{((?:[^{}]|\{[^{}]*\})*)\}/g)];
  expect(frames.length).toBeGreaterThan(0);
  expect(frames.every((match) => !(match[1] ?? '').includes('backdrop-filter'))).toBe(true);
});
