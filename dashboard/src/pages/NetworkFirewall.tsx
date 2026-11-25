// SPDX-License-Identifier: Apache-2.0
// The Firewall section of the Network screen (P-09 part 1, "Firewall: view"): what the box lets in and from
// where, one plain sentence per rule, from GET /v1/network/firewall. Read only. Allow rules with automatic
// revert are part 2 and will appear here as a request the owner approves; there is no control for them yet.
import { OneMind, OneMindError, type FirewallView } from '@onemind/sdk';
import { Button, Card, StatusPill, Table, type Tone } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { Load } from './parts';

type Rule = FirewallView['rules'] extends (infer R)[] | undefined ? R : never;
type Audience = Rule['audience'];

const FROM: Record<Audience, string> = {
  this_machine: 'This box itself',
  mesh: 'Your mesh',
  pod_network: 'Apps on this box',
  lan: 'Home network (LAN)',
  specific_address: 'One address',
  one_interface: 'One connection',
  any_network: 'Any address',
};
const ACTION: Record<Rule['action'], string> = { accept: 'Allow', drop: 'Block', reject: 'Block', jump: 'Check list', goto: 'Check list', return: 'Back', none: 'No effect' };

function exposureTone(e: FirewallView['exposure']): Tone {
  return e === 'lan_and_mesh_only' ? 'ok' : e === 'open_to_internet' || e === 'not_fully_understood' ? 'warn' : 'bad';
}
function exposureLabel(e: FirewallView['exposure']): string {
  return e === 'lan_and_mesh_only' ? 'Never the internet' : e === 'open_to_internet' ? 'Open to the internet' : e === 'no_firewall' ? 'Not protected' : e === 'not_fully_understood' ? 'Not fully checked' : 'Unknown';
}

export function FirewallCard({ client }: { client: OneMind }) {
  const view = usePoll(async () => {
    try {
      return await client.network.firewall();
    } catch (e) {
      if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
      throw e;
    }
  }, 30_000);
  return (
    <Card as="article" title="Firewall">
      <Load res={view} what="Loading the firewall">
        {(v) => {
          if (!v.available) {
            return (
              <p className="om-note om-tone-warn" role="status">
                {v.message ?? 'The firewall could not be read.'} An unreadable firewall is not a safe one: it is simply not known.
              </p>
            );
          }
          const rules = v.rules ?? [];
          const lists = (v.chains ?? []).filter((c) => !c.base);
          const lan = (v.sets ?? []).filter((s) => s.name === 'lan4' || s.name === 'lan6').flatMap((s) => s.elements);
          return (
            <>
              <p>
                <StatusPill tone={exposureTone(v.exposure)} label={exposureLabel(v.exposure)} /> {v.headline}
              </p>
              {(v.open_to_anywhere ?? []).length > 0 && (
                <p className="om-note om-tone-warn" role="status">
                  Open to any address: {(v.open_to_anywhere ?? []).join(', ')}. If you did not choose this, check the rules below marked &quot;Any address&quot;.
                </p>
              )}
              <p className="om-hint">
                Rules are tried top to bottom. {v.default_action === 'drop' ? 'Anything no rule allows is dropped.' : 'Anything no rule blocks is let in.'}
                {lan.length > 0 ? ` "Home network" means ${lan.join(', ')}.` : ''}
                {lists.length > 0 ? ` Lists: ${lists.map((c) => c.name).join(', ')}.` : ''}
              </p>
              <Table<Rule>
                caption="Firewall rules"
                hideCaption
                rows={rules}
                rowKey={(r) => `${r.chain}/${r.position}`}
                empty="No rules are loaded."
                columns={[
                  { key: 'from', header: 'From', render: (r) => FROM[r.audience] ?? r.audience },
                  { key: 'action', header: 'What happens', render: (r) => <StatusPill tone={r.action === 'accept' && r.audience === 'any_network' && r.kind === 'open_port' ? 'warn' : r.action === 'accept' ? 'ok' : 'neutral'} label={ACTION[r.action] ?? r.action} /> },
                  { key: 'summary', header: 'In plain words', render: (r) => r.summary },
                  { key: 'chain', header: 'List', secondary: true, render: (r) => `${r.chain} #${r.position}` },
                ]}
              />
              {(v.other_tables ?? []).length > 0 && (
                <p className="om-hint">
                  Other services keep their own rules ({(v.other_tables ?? []).map((t) => `${t.name}: ${t.rules}`).join(', ')}). They are not listed here.
                </p>
              )}
              {(v.truncated ?? 0) > 0 && (
                <p className="om-note om-tone-warn" role="status">
                  Part of the rules ({v.truncated}) were left out because the list is too long, so this view is not complete.
                </p>
              )}
              {(v.dropped ?? 0) > 0 && (
                <p className="om-note om-tone-warn">
                  {v.dropped} firewall {v.dropped === 1 ? 'entry was' : 'entries were'} left out because the box reported something that did not check out.
                </p>
              )}
              <Button size="sm" variant="ghost" onClick={() => void view.reload()}>
                Refresh firewall
              </Button>
              <p className="om-hint">This only shows the firewall. Opening a port yourself, with an automatic undo if it locks you out, comes next as a request you approve.</p>
            </>
          );
        }}
      </Load>
    </Card>
  );
}
