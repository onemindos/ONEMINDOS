// SPDX-License-Identifier: Apache-2.0
import type { XRFrame, XRLayer, XRSession } from './readiness';

const loads = [100, 500, 2000] as const;
export interface FrameRate {assets: number; fps: number}
export function measureFrames(record: (sample: FrameRate) => void) {
  let phase = 0, intervals = 0;
  let start: number | undefined;
  return {
    assets: () => loads[phase],
    renderedAt(time: number) {
      if (start === undefined) { start = time; return; }
      const assets = loads[phase];
      if (assets === undefined || ++intervals < 90) return;
      if (time > start) {
        record({assets, fps: Math.round(intervals * 10000 / (time - start)) / 10});
        phase++;
      }
      intervals = 0;
      start = undefined;
    },
    trackingLost() { intervals = 0; start = undefined; },
  };
}

function shader(gl: WebGLRenderingContext, program: WebGLProgram, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) throw new Error('The browser could not allocate a shader.');
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  gl.attachShader(program, shader);
  gl.deleteShader(shader);
}

function markerScene(gl: WebGLRenderingContext) {
  const program = gl.createProgram();
  const buffer = gl.createBuffer();
  if (!program || !buffer) throw new Error('The browser could not allocate the marker scene.');
  shader(gl, program, gl.VERTEX_SHADER, `
    attribute vec3 position;
    uniform mat4 projection, view;
    void main() { gl_Position = projection * view * vec4(position, 1.0); gl_PointSize = 5.0; }`);
  shader(gl, program, gl.FRAGMENT_SHADER, `
    precision mediump float;
    void main() { gl_FragColor = vec4(0.15, 0.78, 0.84, 1.0); }`);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('The marker scene shader is unavailable.');
  gl.useProgram(program);
  // Place reference markers in front of the viewer's initial pose. They are the device test load.
  const positions = new Float32Array(2000 * 3);
  for (let i = 0; i < 2000; i++) {
    const slot = (i * 997) % 2000;
    positions.set([(slot % 50 - 24.5) / 25, (Math.floor(slot / 50) - 19.5) / 25, -2], i * 3);
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, 'position');
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 0, 0);
  const projection = gl.getUniformLocation(program, 'projection');
  const viewMatrix = gl.getUniformLocation(program, 'view');
  return (frame: XRFrame, space: object, layer: XRLayer, count: number) => {
    const pose = frame.getViewerPose(space);
    if (!pose) return false;
    gl.bindFramebuffer(gl.FRAMEBUFFER, layer.framebuffer);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    let drew = false;
    for (const view of pose.views) {
      const viewport = layer.getViewport(view);
      if (!viewport) continue;
      gl.viewport(viewport.x, viewport.y, viewport.width, viewport.height);
      gl.uniformMatrix4fv(projection, false, view.projectionMatrix);
      gl.uniformMatrix4fv(viewMatrix, false, view.transform.inverse.matrix);
      gl.drawArrays(gl.POINTS, 0, count);
      drew = true;
    }
    return drew;
  };
}

export async function benchmark(session: XRSession, samples: FrameRate[], signal: AbortSignal) {
  if (signal.aborted) return;
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl', {alpha: true, xrCompatible: true} as WebGLContextAttributes);
  if (!gl) throw new Error('Immersive graphics are unavailable.');
  const lifetime = new AbortController();
  const stop = () => lifetime.abort();
  session.addEventListener('end', stop, {once: true, signal: lifetime.signal});
  signal.addEventListener('abort', stop, {once: true, signal: lifetime.signal});
  try {
    const layerType = (window as Window & {XRWebGLLayer?: new (s: XRSession, gl: WebGLRenderingContext) => XRLayer}).XRWebGLLayer;
    if (!layerType) throw new Error('The browser cannot render the immersive layer.');
    const space = await session.requestReferenceSpace('local');
    if (lifetime.signal.aborted) return;
    const layer = new layerType(session, gl);
    session.updateRenderState({baseLayer: layer});
    const draw = markerScene(gl);
    const frames = measureFrames(sample => samples.push(sample));
    await new Promise<void>((resolve, reject) => {
      const lost = () => reject(new Error('The graphics context was lost.'));
      lifetime.signal.addEventListener('abort', () => resolve(), {once: true});
      canvas.addEventListener('webglcontextlost', lost, {once: true, signal: lifetime.signal});
      const next = (time: number, frame: XRFrame) => {
        try {
          const assets = frames.assets();
          if (lifetime.signal.aborted || assets === undefined) { resolve(); return; }
          if (draw(frame, space, layer, assets)) frames.renderedAt(time);
          else frames.trackingLost();
          if (frames.assets() === undefined) resolve();
          else session.requestAnimationFrame(next);
        } catch (error) { reject(error); }
      };
      session.requestAnimationFrame(next);
    });
  } catch (error) {
    if (!lifetime.signal.aborted) throw error;
  } finally {
    stop();
    gl.getExtension('WEBGL_lose_context')?.loseContext();
  }
}
