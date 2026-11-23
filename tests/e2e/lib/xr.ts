// SPDX-License-Identifier: Apache-2.0
/**
 * A headset without a headset (issue #813). IWER, Meta's Immersive Web Emulation Runtime (MIT, npm
 * `iwer`, pinned in package.json), replaces the browser's WebXR API with an emulated Quest Pro or
 * Quest 3 before any page script runs, so a spec can enter and leave immersive-vr and immersive-ar
 * in headless Chromium and drive the controllers and hands from code.
 *
 * IWER emulates the API, not the speed of a headset: never assert frame rates here. Assert what the
 * page shows and what it drew. `rendererInfo` counts draw calls on every WebGL context in the page,
 * in the shape of three.js `renderer.info.render` (calls, triangles, points, lines), so the same
 * assertions hold whether a screen draws with raw WebGL (today's diagnostics) or through three.js.
 *
 * Any dashboard spec can reuse it: `await emulateHeadset(page, 'metaQuestPro')` before `page.goto`.
 */
import { createRequire } from 'node:module';
import type { Page } from '@playwright/test';

/** The IWER device profiles the XR track proves (the Quest Pro is the founder's headset). */
export const HEADSETS = {
  metaQuestPro: { name: 'Meta Quest Pro', controllerProfile: 'meta-quest-touch-pro', userAgent: 'Quest Pro' },
  metaQuest3: { name: 'Meta Quest 3', controllerProfile: 'meta-quest-touch-plus', userAgent: 'Quest 3' },
} as const;
export type Headset = keyof typeof HEADSETS;

/** IWER's browser bundle (UMD, sets globalThis.IWER, its two dependencies inlined). */
const iwerBundle = () => createRequire(import.meta.url).resolve('iwer/build/iwer.min.js');

/** Chromium flags for WebGL without a GPU: CI runners and headless shells render with SwiftShader. */
export const SOFTWARE_GL_ARGS = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'];

export interface RendererInfo { calls: number; triangles: number; points: number; lines: number; pointBatches: number[] }
export interface InputSourceInfo { handedness: string; profiles: string[]; hand: boolean; gamepad: boolean }
export interface ScriptedInput { controllers: InputSourceInfo[]; hands: InputSourceInfo[]; selects: string[] }

/** Runs in the page before its own scripts (serialised by Playwright: no closures over this module). */
function install({ headset }: { headset: string }) {
  if (window.top !== window) return; // frames inside the page keep the browser's own API
  type Device = Record<string, unknown> & { installRuntime(options: object): void };
  const iwer = (globalThis as unknown as { IWER: Record<string, unknown> }).IWER;
  const Device = iwer.XRDevice as new (config: unknown) => Device;
  const device = new Device(iwer[headset]);
  // Desktop Chromium already has a navigator.xr (with no headset behind it): replace it.
  device.installRuntime({ forceInstall: true });
  const info = { calls: 0, triangles: 0, points: 0, lines: 0, pointBatches: [] as number[] };
  const count = (mode: number, vertices: number, instances = 1) => {
    info.calls++;
    const n = vertices * instances;
    if (mode === 0) { info.points += n; if (!info.pointBatches.includes(vertices)) info.pointBatches.push(vertices); }
    else if (mode === 1) info.lines += n / 2;
    else if (mode === 2) info.lines += n;
    else if (mode === 3) info.lines += n - 1;
    else if (mode === 4) info.triangles += n / 3;
    else if (mode === 5 || mode === 6) info.triangles += n - 2;
  };
  const contexts = [window.WebGLRenderingContext, window.WebGL2RenderingContext].filter(Boolean);
  for (const ctx of contexts) {
    const proto = ctx.prototype as unknown as Record<string, (...args: number[]) => void>;
    const drawArrays = proto.drawArrays, drawElements = proto.drawElements;
    proto.drawArrays = function (mode, first, n) { count(mode, n); return drawArrays.call(this, mode, first, n); };
    proto.drawElements = function (mode, n, type, offset) { count(mode, n); return drawElements.call(this, mode, n, type, offset); };
    if ('drawArraysInstanced' in proto) {
      const instanced = proto.drawArraysInstanced;
      proto.drawArraysInstanced = function (mode, first, n, k) { count(mode, n, k); return instanced.call(this, mode, first, n, k); };
    }
  }
  Object.defineProperty(window, '__onemindXR', { value: { device, info, headset }, configurable: false });
}

/**
 * Put an emulated headset into every page of this test before it loads. Call before `page.goto`.
 * The page then sees `navigator.xr` support both immersive modes and the headset's user agent.
 */
export async function emulateHeadset(page: Page, headset: Headset): Promise<void> {
  await page.addInitScript({ path: iwerBundle() });
  await page.addInitScript(install, { headset });
}

/** Draw calls since the page loaded (three.js renderer.info.render shape, plus each point batch size). */
export async function rendererInfo(page: Page): Promise<RendererInfo> {
  return page.evaluate(() => {
    const { info } = (window as unknown as { __onemindXR: { info: RendererInfo } }).__onemindXR;
    return { ...info, pointBatches: [...info.pointBatches] };
  });
}

/**
 * Whether the emulated headset is in an immersive session right now. The blend mode tells the two
 * modes apart: "opaque" is immersive-vr, "alpha-blend" (the room shows through) is immersive-ar.
 */
export async function headsetSession(page: Page): Promise<{ active: boolean; blendMode: string | null }> {
  return page.evaluate(() => {
    const { device } = (window as unknown as { __onemindXR: { device: { activeSession?: { environmentBlendMode: string } } } }).__onemindXR;
    const session = device.activeSession;
    return { active: !!session, blendMode: session?.environmentBlendMode ?? null };
  });
}

/**
 * Script the headset's inputs inside the running session: aim the right controller and pull its
 * trigger, then switch to hand tracking and pinch with the left hand. Returns the input sources the
 * session saw in each mode and every `select` event it fired, in order, labelled by that mode. WebXR
 * gives hand joints (`hand: true`) only to a session that asked for 'hand-tracking'.
 */
export async function scriptControllersAndHands(page: Page): Promise<ScriptedInput> {
  return page.evaluate(async () => {
    interface Tracked { position: { set(x: number, y: number, z: number): void }; updateButtonValue(id: string, v: number): void; updatePinchValue(v: number): void }
    interface Source { handedness: string; profiles: string[]; hand?: unknown; gamepad?: unknown }
    interface Session extends EventTarget { inputSources: Iterable<Source>; requestAnimationFrame(cb: () => void): number }
    const { device } = (window as unknown as { __onemindXR: { device: {
      activeSession?: Session; primaryInputMode: string;
      controllers: Record<string, Tracked>; hands: Record<string, Tracked>;
    } } }).__onemindXR;
    const session = device.activeSession;
    if (!session) throw new Error('no immersive session is running');
    const frames = (n: number) => new Promise<void>(resolve => {
      let left = n;
      const tick = () => (--left <= 0 ? resolve() : void session.requestAnimationFrame(tick));
      session.requestAnimationFrame(tick);
    });
    const sources = () => [...session.inputSources].map(s => ({
      handedness: s.handedness, profiles: [...s.profiles], hand: !!s.hand, gamepad: !!s.gamepad,
    }));
    const selects: string[] = [];
    let phase = 'controller';
    session.addEventListener('select', e => selects.push(`${phase}-${(e as Event & { inputSource: Source }).inputSource.handedness}`));
    device.primaryInputMode = 'controller';
    device.controllers.right.position.set(0.2, 1.4, -0.4);
    await frames(2);
    const controllers = sources();
    device.controllers.right.updateButtonValue('trigger', 1);
    await frames(2);
    device.controllers.right.updateButtonValue('trigger', 0);
    await frames(2);
    device.primaryInputMode = phase = 'hand';
    await frames(2);
    const hands = sources();
    device.hands.left.updatePinchValue(1);
    await frames(2);
    device.hands.left.updatePinchValue(0);
    await frames(2);
    device.primaryInputMode = 'controller';
    return { controllers, hands, selects };
  });
}

/** Leave the session the way the headset's system menu does: the session ends under the page. */
export async function exitFromHeadset(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const { device } = (window as unknown as { __onemindXR: { device: { activeSession?: { end(): Promise<void> } } } }).__onemindXR;
    await device.activeSession?.end();
  });
}
