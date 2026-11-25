// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { SpatialStatus } from './SpatialStatus';
import Diagnostics from './Diagnostics';
import { benchmark, measureFrames } from './benchmark';
import type { XRSession } from './readiness';
import { HEADSETS, emulateXR, emulatedSession, recordingGL } from './xrTestKit';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const browser = (secure: boolean, vr: boolean, ar: boolean) => emulateXR({secure, vr, ar});

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
  const {info} = recordingGL();
  const {session} = emulatedSession();
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
  expect(info().pointBatches).toEqual([100, 500, 2000]);
  expect(session.end).toHaveBeenCalledOnce();
  expect(fetch).not.toHaveBeenCalled();
});

it.each(Object.entries(HEADSETS))('reports a headset exit mid-run as interrupted (%s)', async (_name, userAgent) => {
  const xr = emulateXR({userAgent});
  const {info} = recordingGL();
  const headset = emulatedSession();
  xr.requestSession.mockResolvedValue(headset.session);
  headset.hold();
  render(<Diagnostics />);
  const start = screen.getByRole('button', {name: 'Start AR test'});
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  await screen.findByText('Session running.');
  await waitFor(() => expect(headset.waiting()).toBe(1));
  headset.step(40); // fewer than the 90 frames of the first sample
  headset.exit();
  await screen.findByText('Session interrupted.');
  const report = JSON.parse(screen.getByTestId('spatial-report').textContent!);
  expect(report.browser).toBe(userAgent);
  expect(report.session).toMatchObject({mode: 'immersive-ar', status: 'interrupted', frameRates: []});
  expect(info()).toMatchObject({pointBatches: [100]});
  expect(info().calls).toBe(40);
  expect(start).toBeEnabled();
  expect(fetch).not.toHaveBeenCalled();
});
