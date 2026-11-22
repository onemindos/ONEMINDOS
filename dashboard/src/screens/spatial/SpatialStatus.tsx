// SPDX-License-Identifier: Apache-2.0
import { Link } from 'react-router';
import { Card } from '@onemind/ui';
import { useReadiness } from './readiness';

export function SpatialStatus() {
  const info = useReadiness();
  const ready = [info?.vr === 'available' && 'VR', info?.ar === 'available' && 'AR'].filter(Boolean);
  let summary = 'Checking this browser…';
  if (info) {
    if (!info.secure) summary = 'Open this page securely to check spatial support';
    else if (ready.length) summary = `Ready for ${ready.join(' and ')}`;
    else summary = info.vr === 'unknown' || info.ar === 'unknown' ? 'Support could not be checked' : 'No immersive modes available';
  }
  return <Card title="Spatial">
    <p aria-live="polite">{summary}</p>
    {info && <dl className="om-facts">
      <div><dt>Connection</dt><dd>{info.secure ? 'Secure' : 'Insecure'}</dd></div>
      <div><dt>App display</dt><dd>{info.standalone ? 'Opened as an installed app' : 'Opened in a browser tab'}</dd></div>
      <div><dt>Virtual reality</dt><dd>{info.vr}</dd></div>
      <div><dt>Augmented reality</dt><dd>{info.ar}</dd></div>
    </dl>}
    <Link to="/spatial/diagnostics">Spatial diagnostics</Link>
  </Card>;
}
