// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { trackBarHeight } from './trackBarHeight';

let fire: () => void;
let disconnected = false;
let frames: Map<number, FrameRequestCallback>;
let nextId: number;

beforeEach(() => {
  disconnected = false;
  frames = new Map();
  nextId = 1;
  vi.stubGlobal('ResizeObserver', class {
    constructor(cb: () => void) { fire = cb; }
    observe() {}
    disconnect() { disconnected = true; }
  });
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { frames.set(nextId, cb); return nextId++; });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => void frames.delete(id));
});
afterEach(() => vi.unstubAllGlobals());

const flush = () => { const all = [...frames.values()]; frames.clear(); all.forEach((cb) => cb(0)); };
function setup() {
  const bar = { offsetHeight: 40 } as HTMLElement;
  const root = document.createElement('div');
  const spy = vi.spyOn(root.style, 'setProperty');
  return { bar, root, spy, stop: trackBarHeight(bar, root, '--h') };
}

describe('trackBarHeight', () => {
  it('defers the write to an animation frame, not the observer callback', () => {
    const { root, spy } = setup();
    fire();
    expect(spy).not.toHaveBeenCalled();
    flush();
    expect(root.style.getPropertyValue('--h')).toBe('40px');
  });

  it('keeps one pending frame and skips unchanged values', () => {
    const { bar, spy } = setup();
    fire(); fire(); fire();
    expect(frames.size).toBe(1);
    flush();
    fire(); flush(); // same height again
    expect(spy).toHaveBeenCalledTimes(1);
    (bar as { offsetHeight: number }).offsetHeight = 56;
    fire(); flush();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('cleanup disconnects and cancels the pending frame', () => {
    const { spy, stop } = setup();
    fire();
    stop();
    expect(disconnected).toBe(true);
    expect(frames.size).toBe(0);
    flush();
    expect(spy).not.toHaveBeenCalled();
  });
});
