// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react';

export type Mode = 'immersive-vr' | 'immersive-ar';
export interface XRView {
  projectionMatrix: Float32Array;
  transform: { inverse: { matrix: Float32Array } };
}
export interface XRFrame {
  getViewerPose(space: object): {views: XRView[]} | null;
}
export interface XRSession extends EventTarget {
  requestReferenceSpace(type: 'local'): Promise<object>;
  requestAnimationFrame(frame: (time: number, frame: XRFrame) => void): number;
  updateRenderState(options: {baseLayer: XRLayer}): void;
  end(): Promise<void>;
}
export interface XRLayer {
  framebuffer: WebGLFramebuffer;
  getViewport(view: XRView): {x: number; y: number; width: number; height: number} | null;
}
interface XRSystem extends EventTarget {
  isSessionSupported(mode: Mode): Promise<boolean>;
  requestSession(mode: Mode): Promise<XRSession>;
}
export function browserXR() {
  return (navigator as Navigator & {xr?: XRSystem}).xr;
}
type Support = 'available' | 'unavailable' | 'unknown';
export async function probe() {
  const secure = window.isSecureContext === true;
  const xr = browserXR();
  const standalone = window.matchMedia?.('(display-mode: standalone)').matches === true ||
    (navigator as Navigator & {standalone?: boolean}).standalone === true;
  async function support(mode: Mode): Promise<Support> {
    if (!secure) return 'unknown';
    if (!xr) return 'unavailable';
    try { return await xr.isSessionSupported(mode) ? 'available' : 'unavailable'; }
    catch { return 'unknown'; }
  }
  const [vr, ar] = await Promise.all([support('immersive-vr'), support('immersive-ar')]);
  return {secure, standalone, vr, ar};
}
export function useReadiness() {
  const [result, setResult] = useState<Awaited<ReturnType<typeof probe>>>();
  useEffect(() => {
    let generation = 0;
    const check = async () => {
      const id = ++generation;
      const result = await probe();
      if (generation === id) setResult(result);
    };
    void check();
    const xr = browserXR();
    xr?.addEventListener?.('devicechange', check);
    return () => { generation++; xr?.removeEventListener?.('devicechange', check); };
  }, []);
  return result;
}
