// SPDX-License-Identifier: Apache-2.0
/**
 * The spatial engine (issue #814): three.js through React Three Fiber, with the WebXR session run by
 * three.js's own WebXRManager (renderer.xr). Only Spatial.tsx imports this file, lazily and only after
 * the #772 probe found an immersive mode, so three.js stays out of the main bundle (bundle-check.mjs
 * proves it at build time).
 *
 * Why not @react-three/xr: 6.6.32 builds with React Three Fiber 9.8.2 and three 0.187, but its store
 * always contains a dynamic import of its IWER emulator, even with `emulate: false`. That put about
 * 5.7 MB of emulator and synthetic-room chunks, with Font Awesome icons (CC-BY-4.0), into dist/, and
 * the dashboard ships only MIT, BSD or Apache-2.0 code.
 *
 * A session starts only from the Enter VR or Enter AR button (requestSession straight from the click).
 * Nothing offers a session or enters a granted one. The scene is empty, asks for no room data (no
 * planes, meshes, anchors or hit tests) and loads no controller or hand models, so nothing is fetched
 * from outside the hub. A headset never approves: there are no action controls here.
 */
import { useEffect, useRef, useState } from 'react';
import type { WebGLRenderer } from 'three';
import { Button, Card } from '@onemind/ui';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { FrameCounter, type FrameSnapshot } from './frameStats';

type Mode = 'immersive-vr' | 'immersive-ar';
const LABEL: Record<Mode, string> = { 'immersive-vr': 'VR', 'immersive-ar': 'AR' };
/** Optional only: the session starts without them. 'local' (seated, at the start pose) is always granted. */
export const SESSION_INIT: XRSessionInit = { optionalFeatures: ['hand-tracking'] };

/** Inside the three.js loop: hands the renderer up and samples every immersive frame. */
function Bridge({ counter, onRenderer }: { counter: FrameCounter; onRenderer: (gl: WebGLRenderer | null) => void }) {
  const gl = useThree(s => s.gl);
  useEffect(() => { onRenderer(gl); return () => onRenderer(null); }, [gl, onRenderer]);
  useFrame((state, _delta, frame) => {
    if (frame) counter.frame(performance.now(), state.gl.info.render);
  });
  return null;
}

function FrameStats({ counter, mode }: { counter: FrameCounter; mode: Mode | null }) {
  const [stats, setStats] = useState<FrameSnapshot>(() => counter.snapshot());
  useEffect(() => {
    const id = window.setInterval(() => setStats(counter.snapshot()), 250);
    return () => window.clearInterval(id);
  }, [counter]);
  const fps = stats.fps === null ? 'measuring' : `${stats.fps} fps`;
  return <output className="om-spatial-stats" data-testid="frame-stats" data-mode={mode ?? 'none'} data-frames={stats.frames}>
    {mode ? `${LABEL[mode]} session` : 'No session'} · {fps} · {stats.frames.toLocaleString()} immersive frames
    · {stats.calls} draw calls · {stats.triangles.toLocaleString()} triangles
  </output>;
}

export default function Engine({ vr, ar }: { vr: boolean; ar: boolean }) {
  const [renderer, setRenderer] = useState<WebGLRenderer | null>(null);
  const [counter] = useState(() => new FrameCounter());
  const [mode, setMode] = useState<Mode | null>(null);
  const [entering, setEntering] = useState(false);
  const [error, setError] = useState<string>();
  const session = useRef<XRSession | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; void session.current?.end().catch(() => {}); session.current = null; };
  }, []);

  async function enter(next: Mode) {
    const xr = navigator.xr;
    if (!renderer || !xr || entering || session.current) return;
    setEntering(true);
    setError(undefined);
    let started: XRSession | undefined;
    try {
      // Requested straight from the click so the browser sees the person's gesture.
      started = await xr.requestSession(next, SESSION_INIT);
      if (!mounted.current) { await started.end(); return; }
      session.current = started;
      started.addEventListener('end', () => {
        if (session.current === started) session.current = null;
        if (mounted.current) setMode(null);
      }, { once: true });
      renderer.xr.setReferenceSpaceType('local');
      await renderer.xr.setSession(started);
      counter.restart();
      if (mounted.current && session.current === started) setMode(next);
    } catch (e) {
      if (started && session.current === started) { session.current = null; await started.end().catch(() => {}); }
      if (mounted.current) setError(e instanceof DOMException || e instanceof Error ? `${e.name}: ${e.message}` : 'The headset did not start a session.');
    } finally {
      if (mounted.current) setEntering(false);
    }
  }
  const busy = entering || mode !== null;
  let status = 'No session. Put on the headset and choose a mode.';
  if (error) status = error;
  else if (entering) status = 'Starting the session…';
  else if (mode) status = `${LABEL[mode]} session running. Exit with the button below or the headset's system controls.`;
  return <Card title="Immersive session">
    <Button disabled={!renderer || busy || !vr} onClick={() => void enter('immersive-vr')}>Enter VR</Button>
    <Button disabled={!renderer || busy || !ar} onClick={() => void enter('immersive-ar')}>Enter AR</Button>
    {mode && <Button onClick={() => void session.current?.end().catch(() => {})}>Exit session</Button>}
    <p role="status">{status}</p>
    <FrameStats counter={counter} mode={mode} />
    <div className="om-spatial-canvas" style={{ height: 240 }}>
      <Canvas frameloop="demand" aria-label="Spatial scene (empty)">
        <Bridge counter={counter} onRenderer={setRenderer} />
      </Canvas>
    </div>
  </Card>;
}
