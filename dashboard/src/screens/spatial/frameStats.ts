// SPDX-License-Identifier: Apache-2.0
/**
 * Frame statistics for the spatial engine (issue #814). The engine feeds one sample per rendered
 * frame from inside the three.js loop (which a headset drives while a session runs); the overlay
 * reads a snapshot a few times a second, so React never re-renders at frame rate.
 */
export interface RenderInfo { calls: number; triangles: number; points: number; lines: number }
export interface FrameSnapshot { frames: number; fps: number | null; calls: number; triangles: number }

/** Frames per second over the last full second of frames; null until a second has been seen. */
export class FrameCounter {
  private frames = 0;
  private windowStart: number | undefined;
  private windowFrames = 0;
  private fps: number | null = null;
  private last: RenderInfo = { calls: 0, triangles: 0, points: 0, lines: 0 };

  frame(time: number, info: RenderInfo) {
    this.frames++;
    this.last = { calls: info.calls, triangles: info.triangles, points: info.points, lines: info.lines };
    if (this.windowStart === undefined) { this.windowStart = time; this.windowFrames = 0; return; }
    this.windowFrames++;
    const elapsed = time - this.windowStart;
    if (elapsed >= 1000) {
      this.fps = Math.round(this.windowFrames * 10000 / elapsed) / 10;
      this.windowStart = time;
      this.windowFrames = 0;
    }
  }

  /** A new session starts the per-second window again; the running frame total stays. */
  restart() { this.windowStart = undefined; this.windowFrames = 0; this.fps = null; }

  snapshot(): FrameSnapshot {
    return { frames: this.frames, fps: this.fps, calls: this.last.calls, triangles: this.last.triangles };
  }
}
