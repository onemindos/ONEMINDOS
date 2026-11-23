// SPDX-License-Identifier: Apache-2.0
// Passwords (#679): the built-in Vaultwarden, set up in the Bitwarden apps people already know.
// Reads only: GET /v1/system-apps (is Passwords on, is it running) and GET /v1/mesh (the box's own
// addresses for it, home network and mesh only). It never writes and never shows a token: the QR holds
// the server address and nothing else, because a vault is locked with the person's own master password,
// which OneMind never sees. A OneMind token is never a sync password.
// The phone card lives in the phone app (wave P); this is the desktop page.
import { Card, PageHeader, QrSvg, StatusPill, type MeshView } from '@onemind/ui';
import type { SystemAppRow } from '../api/client';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load } from './parts';

export const PASSWORDS_APP = 'vaultwarden';

const HEAD = <PageHeader title="Passwords" lede="Your household’s passwords on this box, in the Bitwarden apps you already know. Nothing leaves home." />;

/** The addresses the box serves Passwords on: home network first, then the mesh. Never a public one. */
export function passwordAddresses(mesh: MeshView): { label: string; url: string }[] {
  const link = mesh.apps.find((a) => a.app_id === PASSWORDS_APP);
  if (!link) return [];
  const out = [{ label: 'At home', url: link.lan }];
  if (link.lan_alias && link.lan_alias !== link.lan) out.push({ label: 'At home (short name)', url: link.lan_alias });
  if (mesh.mode !== 'off' && mesh.names.mesh.length > 0) out.push({ label: 'On your mesh', url: link.mesh });
  return out;
}

export function Passwords() {
  const { api, principal } = useSignedIn();
  const person = principal?.kind === 'person';
  const supported = !!(api.systemApps && api.meshView);
  const sys = usePoll<SystemAppRow[]>(() => (person && api.systemApps ? api.systemApps() : Promise.reject(new Error('unsupported'))), 30_000);
  const mesh = usePoll<MeshView>(() => (person && api.meshView ? api.meshView() : Promise.reject(new Error('unsupported'))), 30_000);

  if (!person) {
    return <>{HEAD}<p className="om-note om-tone-warn" role="status">Setting up Passwords needs a signed-in person. Agents and app tokens cannot open this page.</p></>;
  }
  if (!supported) {
    return <>{HEAD}<p role="status">Passwords comes from a real hub. Demo mode has none.</p></>;
  }
  return <div className="dash-stack">
    {HEAD}
    <Load res={sys} what="Reading Passwords">{(rows) => {
      const row = rows.find((r) => r.id === PASSWORDS_APP);
      if (!row) return <p className="om-note om-tone-warn" role="status">This box’s OS does not list Passwords as built in yet. An OS update brings it.</p>;
      if (!row.enabled) {
        return <Card title="Passwords is switched off" aside={<StatusPill tone="neutral" label="Off" />}>
          <p>Your vault is kept on this box. Nothing was deleted. An owner can switch Passwords back on from <a href={href.manage(PASSWORDS_APP)}>Installed</a>, and every Bitwarden app picks up where it left off.</p>
        </Card>;
      }
      if (row.status !== 'installed') {
        return <Card title="Passwords is not running" aside={<StatusPill tone="warn" label={row.status ?? 'Not installed'} />}>
          <p>An owner approves its install once from <a href={href.app(PASSWORDS_APP)}>its Market page</a>. It is built in, so it can be switched off later but never removed.</p>
        </Card>;
      }
      return <Load res={mesh} what="Reading this box’s addresses">{(m) => <Setup mesh={m} row={row} />}</Load>;
    }}</Load>
  </div>;
}

function Setup({ mesh, row }: { mesh: MeshView; row: SystemAppRow }) {
  const addresses = passwordAddresses(mesh);
  if (addresses.length === 0) return <p className="om-note om-tone-warn" role="status">The box has not published an address for Passwords yet. Try again in a minute.</p>;
  const main = addresses[0]!;
  return <>
    <Card title="Server address" aside={<StatusPill tone="ok" label="Running" />}>
      <div className="dash-passwords-address">
        <QrSvg text={main.url} label={`QR code with the Passwords server address ${main.url}`} />
        <dl className="om-facts">
          {addresses.map((a) => <div key={a.url}><dt>{a.label}</dt><dd><code>{a.url}</code></dd></div>)}
          <div><dt>Reach</dt><dd>Only your home network and your mesh. Opening it to the internet needs an owner’s approval.</dd></div>
          <div><dt>Engine</dt><dd>Vaultwarden {row.version ?? ''}, licence {row.license ?? 'not reported'}, unmodified (<a href="https://github.com/dani-garcia/vaultwarden" target="_blank" rel="noopener noreferrer">source code</a>)</dd></div>
        </dl>
      </div>
      {mesh.https && <p className="om-hint">A new phone or computer must trust this box first: open <a href="/v1/tls/ca.crt" download>the box certificate</a> on it.</p>}
    </Card>
    <Card title="Set up the Bitwarden app">
      <ol aria-label="Bitwarden app steps">
        <li>Install the Bitwarden app on your phone or computer, or the Bitwarden browser extension.</li>
        <li>On its sign-in screen, choose <strong>Self-hosted</strong> as the server.</li>
        <li>Scan the QR code, or type the server address shown here.</li>
        <li>Create your account with a master password only you know. OneMind never sees it and cannot reset it, so write it in your emergency kit.</li>
      </ol>
      <p className="om-hint">Your OneMind sign-in is not your vault password. Never type a OneMind token or passkey code into Bitwarden.</p>
      <p className="om-note om-tone-warn" role="note">Not working yet: the box asks for your OneMind sign-in on every app request, and the Bitwarden apps cannot give it, so signing in from them fails until the box lets apps with their own sign-in through on your home network and mesh. That is a separate gateway change.</p>
    </Card>
  </>;
}
