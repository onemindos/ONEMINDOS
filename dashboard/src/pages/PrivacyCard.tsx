// SPDX-License-Identifier: Apache-2.0
// Settings > About, "What leaves this box" (privacy statement, native-features audit b10). Each line that depends on
// how this box is set up is read from the box: the mesh mode (GET /v1/mesh) and whether your own domain is on
// (GET /v1/domains). Two lines are facts about the software itself and say so: it sends no usage data, and an update
// check is a plain download request. Read only; there is nothing to switch here.
import { Card } from '@onemind/ui';
import type { MeshView } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useGateway, viaSdk } from '../lib/gateway';
import { useSignedIn } from '../session';

const REACH: Record<MeshView['mode'], string> = {
  lan: 'Nothing. Machines on your home network reach each other over the encrypted mesh, and nothing is open to the internet.',
  relay: 'Encrypted mesh traffic to your phones and remote machines passes through your own relay server.',
  direct: 'Your router forwards the mesh ports to the box, so the box is reachable from the internet on those ports.',
  hosted: 'A third-party coordination service (Tailscale) is used to connect your devices.',
  off: 'Nothing. This box runs without the private mesh.',
};

export function PrivacyCard() {
  const { token, mock, canDecide } = useSignedIn();
  const owner = !mock && canDecide !== 'no';
  const client = useGateway(token);
  const mesh = usePoll(async () => (owner ? viaSdk(() => client.call<MeshView>({ method: 'GET', path: '/v1/mesh' })) : undefined), 60_000);
  const domains = usePoll(async () => (owner ? viaSdk(() => client.domains.list()) : undefined), 60_000);

  const rows: [string, string][] = [
    ['Usage data and crash reports', 'Nothing. OneMind has no analytics, no crash reporting and no usage statistics: the software contains no code that sends them.'],
    ['Update checks', 'A plain download request (GET) for the list of new versions. The box adds no account, sign-in or device details to it.'],
  ];
  if (!owner) rows.push(['Remote access and your own domain', 'Only the owner can see how this box is reached from outside.']);
  else {
    rows.push(['Remote access', mesh.data ? REACH[mesh.data.mode] : mesh.error ? `Could not read it: ${mesh.error.message}` : 'Reading…']);
    rows.push([
      'Your own domain',
      domains.data
        ? domains.data.enabled
          ? 'On: to verify a domain, the box asks a public DNS server whether your proof record exists. The domain name you ask about is visible to that server.'
          : 'Off. The box makes no lookups for your own domain.'
        : domains.error
          ? `Could not read it: ${domains.error.message}`
          : 'Reading…',
    ]);
  }
  return (
    <Card as="section" title="What leaves this box">
      <p>This is what the OneMind software itself sends out, as this box is set up now. Apps you install follow their own rules.</p>
      <dl className="om-facts">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
