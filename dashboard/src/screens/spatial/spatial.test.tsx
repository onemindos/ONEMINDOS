// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { SpatialStatus } from './SpatialStatus';
import Diagnostics from './Diagnostics';
import { benchmark, measureFrames } from './benchmark';
import type { XRFrame, XRSession } from './readiness';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function browser(secure: boolean, vr: boolean, ar: boolean) {
  const isSessionSupported = vi.fn(async (mode: string) => mode === 'immersive-vr' ? vr : ar);
  const requestSession = vi.fn().mockRejectedValue(new DOMException('Permission denied', 'NotAllowedError'));
  vi.stubGlobal('isSecureContext', secure);
  vi.stubGlobal('navigator', {userAgent: 'test browser', xr: {isSessionSupported, requestSession}});
  vi.stubGlobal('fetch', vi.fn());
  return {isSessionSupported, requestSession};
}

it.each([
  [true, false, false, 'No immersive modes available'],
  [true, true, false, 'Ready for VR'],
  [true, true, true, 'Ready for VR and AR'],
  [false, true, true, 'Open this page securely to check spatial support'],
] as const)('reports real probe results securely (%s, %s, %s)', async (secure, vr, ar, label) => {
  const xr = browser(secure, vr, ar);
  render(<MemoryRouter><SpatialStatus /></MemoryRouter>);
  await screen.findByText(label);
  expect(screen.getByRole('link', {name: 'Spatial diagnostics'})).toHaveAttribute('href', '/spatial/diagnostics');
  expect(xr.isSessionSupported).toHaveBeenCalledTimes(secure ? 2 : 0);
  if (!secure) expect(screen.queryByText(/ready/i)).toBeNull();
  expect(xr.requestSession).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

it('records denied user-initiated session and passkey observation locally', async () => {
  const xr = browser(true, true, false);
  render(<Diagnostics />);
  const button = await screen.findByRole('button', {name: 'Start VR test'});
  await waitFor(() => expect(button).toBeEnabled());
  expect(xr.requestSession).not.toHaveBeenCalled();
  fireEvent.click(button);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('NotAllowedError'), {timeout: 1000});
  fireEvent.change(screen.getByLabelText('Passkey sign-in on this device'), {target: {value: 'succeeded'}});
  const report = JSON.parse(screen.getByTestId('spatial-report').textContent!);
  expect(report.session.status).toBe('failed');
  expect(report.session.startedAt).toBeNull();
  expect(report.session.frameRates).toEqual([]);
  expect(report.passkey.signIn).toBe('succeeded');
  expect(xr.requestSession).toHaveBeenCalledTimes(1);
  expect(fetch).not.toHaveBeenCalled();
});

it('records each asset load from the rendered immersive frames', () => {
  const samples: {assets: number; fps: number}[] = [];
  const frames = measureFrames(sample => samples.push(sample));
  for (let i = 0; i < 300 && frames.assets() !== undefined; i++) {
    frames.renderedAt(i * 20);
  }
  expect(samples).toEqual([100, 500, 2000].map(assets => ({assets, fps: 50})));
});

it('handles a headset exit while obtaining tracking space', async () => {
  const loseContext = vi.fn();
  const gl = {getExtension: () => ({loseContext})} as unknown as WebGLRenderingContext;
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(gl);
  vi.stubGlobal('XRWebGLLayer', class {});
  const events = new EventTarget();
  const session = Object.assign(events, {
    async requestReferenceSpace() {
      events.dispatchEvent(new Event('end'));
      throw new DOMException('Session ended', 'InvalidStateError');
    },
    requestAnimationFrame: vi.fn(), updateRenderState: vi.fn(), end: vi.fn(),
  }) satisfies XRSession;
  await expect(benchmark(session, [], new AbortController().signal)).resolves.toBeUndefined();
  expect(session.requestAnimationFrame).not.toHaveBeenCalled();
  expect(loseContext).toHaveBeenCalledOnce();
});

it('renders the requested marker counts for a granted session and exports the measured FPS', async () => {
  const xr = browser(true, true, false);
  vi.stubGlobal('matchMedia', () => ({matches: true}));
  const gl = {
    createProgram: () => ({}), createShader: () => ({}), createBuffer: () => ({}),
    getProgramParameter: () => true, getAttribLocation: () => 0, getUniformLocation: () => ({}),
    attachShader: vi.fn(), shaderSource: vi.fn(), compileShader: vi.fn(), deleteShader: vi.fn(),
    linkProgram: vi.fn(), useProgram: vi.fn(), bindBuffer: vi.fn(), bufferData: vi.fn(),
    enableVertexAttribArray: vi.fn(), vertexAttribPointer: vi.fn(), bindFramebuffer: vi.fn(),
    clearColor: vi.fn(), clear: vi.fn(), viewport: vi.fn(), uniformMatrix4fv: vi.fn(), drawArrays: vi.fn(),
    getExtension: () => null,
  };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(gl as unknown as WebGLRenderingContext);
  vi.stubGlobal('XRWebGLLayer', class {
    getViewport() {return {x: 0, y: 0, width: 128, height: 128};}
  });
  const matrix = new Float32Array(16);
  const frame: XRFrame = {getViewerPose: () => ({views: [{projectionMatrix: matrix, transform: {inverse: {matrix}}}]})};
  let timestamp = 0;
  const session = Object.assign(new EventTarget(), {
    requestReferenceSpace: async () => ({}), updateRenderState: vi.fn(), end: vi.fn(async () => {}),
    requestAnimationFrame(callback: (time: number, frame: XRFrame) => void) {
      queueMicrotask(() => callback(timestamp += 20, frame));
      return timestamp;
    },
  }) satisfies XRSession;
  xr.requestSession.mockResolvedValue(session);
  render(<Diagnostics />);
  const start = screen.getByRole('button', {name: 'Start VR test'});
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  await screen.findByText('Session completed.');
  const report = JSON.parse(screen.getByTestId('spatial-report').textContent!);
  expect(report.readiness.standalone).toBe(true);
  expect(report.session.startedAt).toEqual(expect.any(String));
  expect(report.session.frameRates).toEqual([100, 500, 2000].map(assets => ({assets, fps: 50})));
  expect([...new Set(gl.drawArrays.mock.calls.map(call => call[2]))]).toEqual([100, 500, 2000]);
  expect(session.end).toHaveBeenCalledOnce();
  expect(fetch).not.toHaveBeenCalled();
});
