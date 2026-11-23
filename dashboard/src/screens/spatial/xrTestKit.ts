// SPDX-License-Identifier: Apache-2.0
/**
 * Test-only kit for the spatial screens' unit tests (issue #813); never imported by app code.
 * jsdom has no WebXR and no WebGL, so these stand in for a headset in vitest: a browser that offers
 * the immersive modes, a session that delivers frames on demand, and a WebGL context that records
 * what was drawn. `info()` uses the shape of three.js `renderer.info.render`, like the Playwright
 * emulator helper in tests/e2e/lib/xr.ts, so unit and browser tests assert the same thing: what was
 * drawn, never the frame rate. The browser suite (tests/e2e/spatial) runs the real dashboard under
 * IWER's Quest Pro and Quest 3 profiles.
 */
import { vi } from 'vitest';
import type { Mode, XRFrame, XRSession } from './readiness';

/** User agents of the headsets the XR track proves, as IWER's profiles report them. */
export const HEADSETS = {
  questPro: 'Mozilla/5.0 (X11; Linux x86_64; Quest Pro) AppleWebKit/537.36 (KHTML, like Gecko) OculusBrowser/33.0.0.x.x.x Chrome/126.0.6478.122 VR Safari/537.36',
  quest3: 'Mozilla/5.0 (X11; Linux x86_64; Quest 3) AppleWebKit/537.36 (KHTML, like Gecko) OculusBrowser/33.0.0.x.x.x Chrome/126.0.6478.122 VR Safari/537.36',
} as const;

/** A browser whose navigator.xr offers the given modes. requestSession is denied until a test grants one. */
export function emulateXR({ secure = true, vr = true, ar = true, userAgent = 'test browser' } = {}) {
  const isSessionSupported = vi.fn(async (mode: Mode) => (mode === 'immersive-vr' ? vr : ar));
  const requestSession = vi.fn<(mode: Mode) => Promise<XRSession>>().mockRejectedValue(new DOMException('Permission denied', 'NotAllowedError'));
  vi.stubGlobal('isSecureContext', secure);
  vi.stubGlobal('navigator', { userAgent, xr: { isSessionSupported, requestSession } });
  vi.stubGlobal('fetch', vi.fn());
  return { isSessionSupported, requestSession };
}

/** A WebGL context that records draws; installed for every canvas. */
export function recordingGL() {
  const drawArrays = vi.fn<(mode: number, first: number, count: number) => void>();
  const gl = {
    POINTS: 0,
    createProgram: () => ({}), createShader: () => ({}), createBuffer: () => ({}),
    getProgramParameter: () => true, getAttribLocation: () => 0, getUniformLocation: () => ({}),
    attachShader: vi.fn(), shaderSource: vi.fn(), compileShader: vi.fn(), deleteShader: vi.fn(),
    linkProgram: vi.fn(), useProgram: vi.fn(), bindBuffer: vi.fn(), bufferData: vi.fn(),
    enableVertexAttribArray: vi.fn(), vertexAttribPointer: vi.fn(), bindFramebuffer: vi.fn(),
    clearColor: vi.fn(), clear: vi.fn(), viewport: vi.fn(), uniformMatrix4fv: vi.fn(), drawArrays,
    getExtension: () => null,
  };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(gl as unknown as WebGLRenderingContext);
  vi.stubGlobal('XRWebGLLayer', class { getViewport() { return { x: 0, y: 0, width: 128, height: 128 }; } });
  const info = () => {
    const calls = drawArrays.mock.calls;
    const points = calls.filter(c => c[0] === gl.POINTS).map(c => c[2]);
    return { calls: calls.length, points: points.reduce((a, b) => a + b, 0), pointBatches: [...new Set(points)] };
  };
  return { gl, info };
}

/**
 * An immersive session that renders a frame every 20 ms of emulated time, as fast as the page asks.
 * After `hold()` frames wait until `step(n)` hands them out, so a test can act mid-run; `exit()`
 * leaves the session the way the headset's system menu does (an `end` event under the page).
 */
export function emulatedSession() {
  const matrix = new Float32Array(16);
  const frame: XRFrame = { getViewerPose: () => ({ views: [{ projectionMatrix: matrix, transform: { inverse: { matrix } } }] }) };
  let time = 0, held = false;
  const waiting: Array<() => void> = [];
  const session = Object.assign(new EventTarget(), {
    requestReferenceSpace: async () => ({}), updateRenderState: vi.fn(), end: vi.fn(async () => {}),
    requestAnimationFrame(callback: (time: number, frame: XRFrame) => void) {
      const run = () => callback(time += 20, frame);
      if (held) waiting.push(run); else queueMicrotask(run);
      return time;
    },
  }) satisfies XRSession;
  return {
    session,
    hold() { held = true; },
    /** Frames the page has asked for and not yet received. */
    waiting: () => waiting.length,
    step(n: number) { for (let i = 0; i < n && waiting.length; i++) waiting.shift()!(); },
    exit() { session.dispatchEvent(new Event('end')); waiting.splice(0).forEach(run => queueMicrotask(run)); },
  };
}
