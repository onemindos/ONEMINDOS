// SPDX-License-Identifier: Apache-2.0
// Settings > About, "What leaves this box" (privacy statement, native-features audit b10). Each line that depends on
// how this box is set up is read from the box: the mesh mode (GET /v1/mesh), whether your own domain is on
// (GET /v1/domains) and the community catalogue sources (GET /v1/sources). The lines about the software itself say so:
// it sends no usage data, and update checks and downloads are plain requests. The card names what it covers and says
// it is the main list, not a promise of every packet. Read only; there is nothing to switch here.
import { Card } from '@onemind/ui';
import type { MeshView } from '@onemind/ui';
import type { ApiError } from '../api/types';
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

// Say a failed read in words; a 403 means this person is not the owner, which is not an error to show.
const refused = (e: ApiError | undefined, data: unknown) => e?.status === 403 && data === undefined;
const ONLY_OWNER = 'Only the owner can see how this box is reached from outside.';

export function PrivacyCard() {
  const { token, api, mock, canDecide } = useSignedIn();
  const owner = !mock && canDecide !== 'no';
  const client = useGateway(token);
  const mesh = usePoll(async () => (owner && api.meshView ? api.meshView() : undefined), 60_000);
  const domains = usePoll(async () => (owner ? viaSdk(() => client.domains.list()) : undefined), 60_000);
  // Community sources are readable by every signed-in person; the box fetches each one with git when it is added or refreshed.
  const sources = usePoll(async () => (!mock && api.sources ? api.sources() : undefined), 60_000);

  const rows: [string, string][] = [
    ['Usage data and crash reports', 'Nothing. OneMind has no analytics, no crash reporting and no usage statistics: the software contains no code that sends them.'],
    ['Update checks', 'A plain download request (GET) for the list of new versions. The box adds no account, sign-in or device details to it.'],
    ['Update downloads', 'When you install an update, the box downloads the update file from the update server. The web address of that file contains the box type and the version number you are updating to.'],
    ['Installing apps', 'When you install an app, the box pulls its container images from the registry named in the app, and the registry sees the box asking for that image.'],
    sources.data
      ? [
          'Community catalogue sources',
          sources.data.length
            ? `The box fetches these sources with git, so each host sees the box asking for its repository: ${sources.data.map((s) => `${s.name} (${s.url})`).join('; ')}.`
            : 'None added. The box fetches no community catalogue.',
        ]
      : ['Community catalogue sources', sources.error ? `Could not read it: ${sources.error.message}` : 'Reading…'],
  ];
  if (!owner) rows.push(['Remote access and your own domain', ONLY_OWNER]);
  else {
    rows.push([
      'Remote access',
      mesh.data ? REACH[mesh.data.mode] : refused(mesh.error, mesh.data) ? ONLY_OWNER : mesh.error ? `Could not read it: ${mesh.error.message}` : 'Reading…',
    ]);
    rows.push([
      'Your own domain',
      domains.data
        ? domains.data.enabled
          ? 'On: to verify a domain, the box asks the DNS server set for this box (by default 1.1.1.1) whether your proof record exists. The domain name you ask about is visible to that server.'
          : 'Off. The box makes no lookups for your own domain.'
        : refused(domains.error, domains.data)
          ? 'Only the owner can see whether your own domain is on.'
          : domains.error
            ? `Could not read it: ${domains.error.message}`
            : 'Reading…',
    ]);
  }
  return (
    <Card as="section" title="What leaves this box">
      <p>These are the main things the OneMind software itself sends out, as this box is set up now. Apps you install follow their own rules.</p>
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
