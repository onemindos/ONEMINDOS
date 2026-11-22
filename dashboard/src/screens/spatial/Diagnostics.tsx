// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from 'react';
import { Button, Card, PageHeader } from '@onemind/ui';
import { benchmark, type FrameRate } from './benchmark';
import { browserXR, useReadiness, type Mode, type XRSession } from './readiness';

interface SessionReport {
  mode: Mode | null;
  status: 'untested' | 'requesting' | 'running' | 'completed' | 'interrupted' | 'failed';
  startedAt: string | null;
  frameRates: FrameRate[];
  error?: string;
}
export default function Diagnostics() {
  const readiness = useReadiness();
  const [session, setSession] = useState<SessionReport>({status: 'untested', mode: null, startedAt: null, frameRates: []});
  const [authenticator, setAuthenticator] = useState<boolean | null>(null);
  const [signIn, setSignIn] = useState('untested');
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    let current = true;
    window.PublicKeyCredential?.isUserVerifyingPlatformAuthenticatorAvailable?.()
      .then(value => { if (current) setAuthenticator(value); }, () => {});
    return () => { current = false; pending.current?.abort(); pending.current = null; };
  }, []);
  async function start(mode: Mode) {
    const xr = browserXR();
    if (pending.current || !window.isSecureContext || !xr) return;
    const controller = new AbortController();
    pending.current = controller;
    const report: SessionReport = {mode, status: 'requesting', startedAt: null, frameRates: []};
    const update = () => { if (!controller.signal.aborted) setSession({...report, frameRates: [...report.frameRates]}); };
    update();
    let immersive: XRSession | undefined;
    try {
      // Request directly from the click to preserve the browser's transient user activation.
      immersive = await xr.requestSession(mode);
      if (controller.signal.aborted) return;
      report.startedAt = new Date().toISOString();
      report.status = 'running';
      update();
      await benchmark(immersive, report.frameRates, controller.signal);
      report.status = report.frameRates.length === 3 ? 'completed' : 'interrupted';
    } catch (error) {
      report.status = 'failed';
      report.error = error instanceof DOMException || error instanceof Error
        ? `${error.name}: ${error.message}` : 'The spatial test failed.';
    } finally {
      await immersive?.end().catch(() => {});
      update();
      controller.abort();
      if (pending.current === controller) pending.current = null;
    }
  }
  const json = JSON.stringify({
    browser: navigator.userAgent, readiness: readiness ?? null, session,
    passkey: {platformAuthenticatorAvailable: authenticator, signIn},
  }, null, 2);
  const active = session.status === 'requesting' || session.status === 'running';
  return <>
    <PageHeader title="Spatial diagnostics" lede="Measure this browser and headset using 100, 500 and 2,000 reference markers." />
    <Card title="Immersive session">
      <p>Choose a mode to enter the headset. You can exit using its system controls.</p>
      <Button disabled={active || readiness?.vr !== 'available'} onClick={() => void start('immersive-vr')}>Start VR test</Button>
      <Button disabled={active || readiness?.ar !== 'available'} onClick={() => void start('immersive-ar')}>Start AR test</Button>
      <p role="status">{session.error ?? (session.status === 'untested' ? 'No session started.' : `Session ${session.status}.`)}</p>
      {session.frameRates.length > 0 && <ul>{session.frameRates.map(s => <li key={s.assets}>{s.assets.toLocaleString()} markers · {s.fps} fps</li>)}</ul>}
    </Card>
    <Card title="Device report">
      <label>Passkey sign-in on this device <select value={signIn} onChange={e => setSignIn(e.target.value)}>
        <option value="untested">Untested</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option>
      </select></label>
      <p>The report stays in this tab until you save a copy.</p>
      <a download="onemind-spatial.json" href={`data:application/json;charset=utf-8,${encodeURIComponent(json)}`}>Save JSON</a>
      <details><summary>View JSON</summary><pre data-testid="spatial-report">{json}</pre></details>
    </Card>
  </>;
}
