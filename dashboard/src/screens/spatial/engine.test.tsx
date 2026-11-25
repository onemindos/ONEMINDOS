// SPDX-License-Identifier: Apache-2.0
// The /spatial page and its engine without a GPU: jsdom has no WebGL, so React Three Fiber's canvas and
// the three.js renderer are stood in for here (test-only). The real engine enters VR and AR under IWER
// in tests/e2e/spatial/engine.spec.ts.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { Mode } from './readiness';
import { emulateXR, emulatedSession } from './xrTestKit';

const engine = vi.hoisted(() => ({
  loaded: false,
  gl: { xr: { setReferenceSpaceType: vi.fn(), setSession: vi.fn(async () => {}) }, info: { render: { calls: 0, triangles: 0, points: 0, lines: 0 } } },
}));
vi.mock('@react-three/fiber', () => {
  engine.loaded = true;
  return {
    Canvas: ({ children }: { children: ReactNode }) => children,
    useThree: (select: (s: { gl: typeof engine.gl }) => unknown) => select({ gl: engine.gl }),
    useFrame: () => {},
  };
});

beforeEach(() => {
  vi.resetModules();
  engine.loaded = false;
  engine.gl.xr.setReferenceSpaceType.mockClear();
  engine.gl.xr.setSession.mockClear();
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function openSpatial() {
  const { default: Spatial } = await import('./Spatial');
  return render(<MemoryRouter><Spatial /></MemoryRouter>);
}

/** A session that ends like a real one: end() fires the 'end' event. */
function grantSessions(requestSession: ReturnType<typeof emulateXR>['requestSession']) {
  const sessions: ReturnType<typeof emulatedSession>['session'][] = [];
  requestSession.mockImplementation(async () => {
    const { session } = emulatedSession();
    session.end.mockImplementation(async () => { session.dispatchEvent(new Event('end')); });
    sessions.push(session);
    return session;
  });
  return sessions;
}

async function engineReady(name: string) {
  const button = await screen.findByRole('button', { name });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

it('without an immersive mode says so and never downloads the 3D engine', async () => {
  emulateXR({ vr: false, ar: false });
  await openSpatial();
  await screen.findByText(/This browser offers no immersive mode/);
  expect(screen.queryByRole('button', { name: 'Enter VR' })).toBeNull();
  expect(engine.loaded).toBe(false);
  expect(screen.getByRole('link', { name: 'Spatial diagnostics' })).toHaveAttribute('href', '/spatial/diagnostics');
});

it('on an insecure page never loads the engine', async () => {
  emulateXR({ secure: false });
  await openSpatial();
  await screen.findByText('Open this page securely to use spatial mode.');
  expect(engine.loaded).toBe(false);
});

it('loads the engine after the probe, starts nothing on its own and enters VR only from the button', async () => {
  const browser = emulateXR({ vr: true, ar: false });
  const sessions = grantSessions(browser.requestSession);
  await openSpatial();
  const enterVR = await engineReady('Enter VR');
  expect(engine.loaded).toBe(true);
  expect(screen.getByRole('button', { name: 'Enter AR' })).toBeDisabled();
  expect(browser.requestSession).not.toHaveBeenCalled();
  expect(screen.getByTestId('frame-stats')).toHaveAttribute('data-mode', 'none');

  fireEvent.click(enterVR);
  await screen.findByText(/VR session running/);
  expect(browser.requestSession).toHaveBeenCalledTimes(1);
  expect(browser.requestSession).toHaveBeenCalledWith('immersive-vr', { optionalFeatures: ['hand-tracking'] });
  expect(engine.gl.xr.setReferenceSpaceType).toHaveBeenCalledWith('local');
  expect(engine.gl.xr.setSession).toHaveBeenCalledWith(sessions[0]);
  expect(screen.getByTestId('frame-stats')).toHaveAttribute('data-mode', 'immersive-vr');
  expect(enterVR).toBeDisabled();

  fireEvent.click(screen.getByRole('button', { name: 'Exit session' }));
  await waitFor(() => expect(screen.getByTestId('frame-stats')).toHaveAttribute('data-mode', 'none'));
  expect(sessions[0]!.end).toHaveBeenCalledTimes(1);
  expect(enterVR).toBeEnabled();
  expect(fetch).not.toHaveBeenCalled();
});

it('enters AR, notices a headset exit and shows a refused session', async () => {
  const browser = emulateXR({ vr: true, ar: true });
  const sessions = grantSessions(browser.requestSession);
  await openSpatial();
  fireEvent.click(await engineReady('Enter AR'));
  await screen.findByText(/AR session running/);
  expect(browser.requestSession).toHaveBeenLastCalledWith('immersive-ar' satisfies Mode, expect.anything());
  act(() => { sessions[0]!.dispatchEvent(new Event('end')); }); // the headset's system menu ended it
  await screen.findByText(/^No session\./);
  browser.requestSession.mockRejectedValue(new DOMException('Permission denied', 'NotAllowedError'));
  fireEvent.click(screen.getByRole('button', { name: 'Enter VR' }));
  await screen.findByText('NotAllowedError: Permission denied');
  expect(screen.getByRole('button', { name: 'Enter VR' })).toBeEnabled();
});

it('ends the session when three.js cannot take it, and when the page closes', async () => {
  const browser = emulateXR({ vr: true, ar: false });
  const sessions = grantSessions(browser.requestSession);
  engine.gl.xr.setSession.mockRejectedValueOnce(new Error('no reference space'));
  const view = await openSpatial();
  const enterVR = await engineReady('Enter VR');
  fireEvent.click(enterVR);
  await screen.findByText('Error: no reference space');
  expect(sessions[0]!.end).toHaveBeenCalledTimes(1);
  fireEvent.click(enterVR);
  await screen.findByText(/VR session running/);
  view.unmount();
  expect(sessions[1]!.end).toHaveBeenCalledTimes(1);
});
