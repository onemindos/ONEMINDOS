// SPDX-License-Identifier: Apache-2.0
/**
 * The headset emulator helper itself (lib/xr.ts), on a blank secure page: no hub needed, so it runs
 * wherever Chromium runs. It proves the helper is installed before page scripts, that each profile
 * offers both immersive modes with its own controllers, and that the draw counter and the scripted
 * controllers and hands report what happened. diagnostics.spec.ts uses the same helper on the hub.
 */
import { expect, test } from '@playwright/test';
import { HEADSETS, emulateHeadset, exitFromHeadset, headsetSession, rendererInfo, scriptControllersAndHands, type Headset } from '../lib/xr';

// A page the test serves itself, on an https origin so it is a secure context (WebXR needs one).
const BLANK = 'https://xr-emulator.test/';

for (const headset of Object.keys(HEADSETS) as Headset[]) {
  const profile = HEADSETS[headset];
  test.describe(profile.name, () => {
    test.beforeEach(async ({ page }) => {
      await page.route(BLANK, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>xr</title><canvas></canvas>' }));
      await emulateHeadset(page, headset);
      await page.goto(BLANK);
    });

    test('is in place before the page runs and offers both immersive modes', async ({ page }) => {
      const seen = await page.evaluate(async () => {
        const xr = (navigator as Navigator & { xr: { isSessionSupported(m: string): Promise<boolean> } }).xr;
        return {
          secure: window.isSecureContext, userAgent: navigator.userAgent,
          vr: await xr.isSessionSupported('immersive-vr'), ar: await xr.isSessionSupported('immersive-ar'),
        };
      });
      expect(seen).toMatchObject({ secure: true, vr: true, ar: true });
      expect(seen.userAgent).toContain(profile.userAgent);
      expect(await headsetSession(page)).toEqual({ active: false, blendMode: null });
    });

    for (const [mode, blendMode] of [['immersive-vr', 'opaque'], ['immersive-ar', 'alpha-blend']] as const) {
      for (const handTracking of [true, false]) {
        test(`${mode}${handTracking ? ' with hand-tracking' : ''}: counts draws, scripts controllers and hands, exits`, async ({ page }) => {
          // A minimal immersive page: one session, a WebGL layer, 7 points drawn per frame.
          await page.evaluate(async ({ mode, handTracking }) => {
            interface Session { updateRenderState(s: object): void; requestAnimationFrame(cb: () => void): number }
            const xr = (navigator as unknown as { xr: { requestSession(m: string, o: object): Promise<Session> } }).xr;
            const session = await xr.requestSession(mode, { optionalFeatures: handTracking ? ['hand-tracking'] : [] });
            const gl = document.querySelector('canvas')!.getContext('webgl', { xrCompatible: true } as WebGLContextAttributes)!;
            const Layer = (window as unknown as { XRWebGLLayer: new (s: Session, g: WebGLRenderingContext) => object }).XRWebGLLayer;
            session.updateRenderState({ baseLayer: new Layer(session, gl) });
            const draw = () => { gl.drawArrays(gl.POINTS, 0, 7); session.requestAnimationFrame(draw); };
            session.requestAnimationFrame(draw);
          }, { mode, handTracking });
          expect(await headsetSession(page)).toEqual({ active: true, blendMode });

          const input = await scriptControllersAndHands(page);
          expect(input.controllers.map(s => s.handedness).sort()).toEqual(['left', 'right']);
          for (const s of input.controllers) expect(s).toMatchObject({ hand: false, gamepad: true, profiles: expect.arrayContaining([profile.controllerProfile]) });
          if (handTracking) {
            expect(input.hands.map(s => s.handedness).sort()).toEqual(['left', 'right']);
            for (const s of input.hands) expect(s).toMatchObject({ hand: true, profiles: expect.arrayContaining(['generic-hand']) });
          } else {
            // Hand joints only for a session that asked for 'hand-tracking'; the pinch still selects.
            expect(input.hands.filter(s => s.hand)).toEqual([]);
          }
          expect(input.selects).toEqual(['controller-right', 'hand-left']);

          const info = await rendererInfo(page);
          expect(info.pointBatches).toEqual([7]);
          expect(info.calls).toBeGreaterThanOrEqual(12); // the input script waited 12 frames
          expect(info.points).toBeGreaterThanOrEqual(12 * 7);

          await exitFromHeadset(page);
          expect(await headsetSession(page)).toEqual({ active: false, blendMode: null });
        });
      }
    }
  });
}
