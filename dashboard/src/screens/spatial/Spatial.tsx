// SPDX-License-Identifier: Apache-2.0
/**
 * /spatial (issue #814). This page is its own lazy chunk and imports no three.js: the engine chunk
 * (Engine.tsx with three.js, React Three Fiber and @react-three/xr) is requested only after the #772
 * probe() finds an immersive mode, so a browser without one never downloads it.
 */
import { lazy, Suspense } from 'react';
import { Link } from 'react-router';
import { Card, PageHeader } from '@onemind/ui';
import { useReadiness } from './readiness';

const Engine = lazy(() => import('./Engine'));

export default function Spatial() {
  const readiness = useReadiness();
  const vr = readiness?.vr === 'available', ar = readiness?.ar === 'available';
  let body;
  if (!readiness) body = <p role="status">Checking this browser…</p>;
  else if (vr || ar) {
    body = <Suspense fallback={<p role="status">Loading the 3D engine…</p>}><Engine vr={vr} ar={ar} /></Suspense>;
  } else {
    const why = !readiness.secure ? 'Open this page securely to use spatial mode.'
      : readiness.vr === 'unknown' || readiness.ar === 'unknown' ? 'Spatial support could not be checked in this browser.'
        : 'This browser offers no immersive mode. Open OneMind in your headset\'s browser.';
    body = <Card title="Immersive session"><p role="status">{why}</p></Card>;
  }
  return <>
    <PageHeader title="Spatial" lede="Your hub in a headset. A session starts only when you choose Enter VR or Enter AR." />
    {body}
    <p><Link to="/spatial/diagnostics">Spatial diagnostics</Link></p>
  </>;
}
