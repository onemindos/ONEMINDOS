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
  it('sets the variable synchronously at setup, before any frame runs', () => {
    const { root, spy } = setup();
    expect(root.style.getPropertyValue('--h')).toBe('40px');
    expect(frames.size).toBe(0);
    fire(); flush(); // observer's initial notification, same value: no second write
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('defers later changes to an animation frame, not the observer callback', () => {
    const { bar, root, spy } = setup();
    (bar as { offsetHeight: number }).offsetHeight = 56;
    fire();
    expect(spy).toHaveBeenCalledTimes(1);
    flush();
    expect(root.style.getPropertyValue('--h')).toBe('56px');
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
    const { bar, spy, stop } = setup();
    (bar as { offsetHeight: number }).offsetHeight = 56;
    fire();
    stop();
    expect(disconnected).toBe(true);
    expect(frames.size).toBe(0);
    flush();
    expect(spy).toHaveBeenCalledTimes(1); // only the setup write
  });
});
