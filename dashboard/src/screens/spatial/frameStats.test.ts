// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { FrameCounter } from './frameStats';

const info = (calls: number, triangles = 0) => ({ calls, triangles, points: 0, lines: 0 });

it('counts immersive frames and reports frames per second once a full second has passed', () => {
  const counter = new FrameCounter();
  expect(counter.snapshot()).toEqual({ frames: 0, fps: null, calls: 0, triangles: 0 });
  for (let i = 0; i <= 72; i++) counter.frame(1000 + i * (1000 / 72), info(i === 72 ? 3 : 0, i === 72 ? 12 : 0));
  expect(counter.snapshot()).toEqual({ frames: 73, fps: 72, calls: 3, triangles: 12 });
});

it('starts the per-second window again for a new session but keeps the frame total', () => {
  const counter = new FrameCounter();
  for (let i = 0; i <= 90; i++) counter.frame(i * (1000 / 90), info(0));
  expect(counter.snapshot().fps).toBe(90);
  counter.restart();
  counter.frame(50_000, info(1));
  expect(counter.snapshot()).toEqual({ frames: 92, fps: null, calls: 1, triangles: 0 });
});
