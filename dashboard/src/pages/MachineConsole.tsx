// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router';
import { OneMind, OneMindError, type paths } from '@onemind/sdk';
import { Button, PageHeader } from '@onemind/ui';
import RFB from '@novnc/novnc';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';

export function MachineConsoleWindow() {
  const { name = '' } = useParams();
  const { role } = useShell();
  const { token, mock } = useSignedIn();
  if (role === undefined) return <p role="status">Checking your role…</p>;
  if (mock || role !== 'owner') return <p role="alert">Sign in as the box owner to open a machine console.</p>;
  if (!/^[a-z][a-z0-9-]{0,38}[a-z0-9]$/.test(name)) return <p role="alert">Invalid machine name.</p>;
  return <MachineConsole key={name} name={name} token={token} />;
}

export function MachineConsole({ name, token }: { name: string; token: string }) {
  const frame = useRef<HTMLElement>(null);
  const display = useRef<HTMLDivElement>(null);
  const [viewOnly, setViewOnly] = useState(false);
  const [status, setStatus] = useState('Connecting…');
  const [error, setError] = useState('');
  const [fullscreenError, setFullscreenError] = useState('');

  useEffect(() => {
    let live = true;
    let superseded = false;
    let client: RFB | undefined;
    let socket: WebSocket | undefined;
    const onClose = (event: CloseEvent) => {
      if (live && event.code === 4001) {
        superseded = true;
        setStatus('Another console took over.');
      }
    };
    const onConnect = () => { if (live) setStatus('Connected'); };
    const onDisconnect = () => { if (live && !superseded) setStatus('Disconnected'); };
    async function connect() {
      setStatus('Connecting…');
      setError('');
      try {
        // A canceled mount, including StrictMode's initial replay, needs no ticket.
        await Promise.resolve();
        if (!live) return;
        const sdk = new OneMind({ baseUrl: window.location.origin, token });
        const route = '/v1/machines/{name}/console' satisfies keyof paths;
        const path = route.replace('{name}', encodeURIComponent(name));
        const grant = await sdk.call<unknown>({ method: 'POST', path });
        if (!live || !display.current) return;
        // Bind the ticket to this hub and machine, including when the gateway returns a malformed path.
        if (!grant || typeof grant !== 'object' || !('machine' in grant) || grant.machine !== name ||
          !('ticket' in grant) || typeof grant.ticket !== 'string' || !grant.ticket ||
          !('path' in grant) || grant.path !== path + '/ws') throw new Error('Invalid console ticket.');
        const url = new URL(grant.path, window.location.origin);
        url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        url.searchParams.set('ticket', grant.ticket);
        if (viewOnly) url.searchParams.set('view', '1');
        socket = new WebSocket(url, 'binary');
        // noVNC's disconnect event omits the WebSocket close code. Keep the broker's takeover reason.
        socket.addEventListener('close', onClose);
        client = new RFB(display.current, socket);
        client.viewOnly = viewOnly;
        client.scaleViewport = true;
        client.addEventListener('connect', onConnect);
        client.addEventListener('disconnect', onDisconnect);
      } catch (e) {
        socket?.close();
        if (!live) return;
        setError(e instanceof OneMindError && e.status === 409 ? 'Start the machine before opening its console.' :
          e instanceof OneMindError && e.status === 403 ? 'Only an owner can open this console.' : 'Could not open the machine console.');
      }
    }
    void connect();
    return () => {
      live = false;
      socket?.removeEventListener('close', onClose);
      client?.removeEventListener('connect', onConnect);
      client?.removeEventListener('disconnect', onDisconnect);
      client?.disconnect();
      socket?.close();
    };
  }, [name, token, viewOnly]);

  async function fullscreen() {
    try {
      setFullscreenError('');
      await frame.current?.requestFullscreen();
    } catch { setFullscreenError('Fullscreen is unavailable in this browser.'); }
  }

  return <section ref={frame} className="dash-stack" style={{ background: 'var(--om-color-surface)', overflow: 'auto' }}>
    <PageHeader title={name + ' console'} actions={<Link to="/machines">Back to Machines</Link>} />
    <div className="om-row">
      <label><input type="checkbox" checked={viewOnly} disabled={status !== 'Connected' || !!error}
        onChange={(event) => setViewOnly(event.target.checked)} /> View only</label>
      <Button size="sm" disabled={!document.fullscreenEnabled} onClick={() => void fullscreen()}>Fullscreen</Button>
    </div>
    {error ? <p role="alert">{error}</p> : <p role="status">{status}</p>}
    {fullscreenError && <p role="alert">{fullscreenError}</p>}
    <div ref={display} role="region" aria-label={name + ' display'} style={{ height: '65vh', minHeight: '12rem', flex: '1 1 auto', background: '#000' }} />
  </section>;
}
