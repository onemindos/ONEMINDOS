// SPDX-License-Identifier: Apache-2.0
// Settings (IA §2.10): people, tokens and agents, security posture, remote access, appearance.
import { Button, Card, PageHeader, StatusPill, Table, ThemeSwitch, formatAgo, secondsSince } from '../../../src';
import { Section } from '../bits';
import { NOW, people, posture, tokens } from '../fixtures';

export function Settings() {
  return (
    <>
      <PageHeader title="Settings" />
      <Section title="Security posture" aside={<StatusPill tone="warn" label="1 thing to check" />}>
        <Card>
          <ul className="d-list">
            {posture.map((p) => (
              <li key={p.item}>
                <span className="d-list-main">
                  <strong>{p.item}</strong>
                  <br />
                  <span className="om-hint">{p.detail}</span>
                </span>
                <StatusPill tone={p.state} label={p.state === 'ok' ? 'Good' : 'Check'} />
              </li>
            ))}
          </ul>
        </Card>
      </Section>
      <Section title="People" aside={<Button size="sm" icon="plus">Invite</Button>}>
        <Table
          caption="People"
          hideCaption
          rowKey={(r) => r.id}
          columns={[
            { key: 'name', header: 'Name', render: (r) => <strong>{r.name}</strong> },
            { key: 'role', header: 'Role', render: (r) => <StatusPill tone={r.role === 'owner' ? 'info' : 'neutral'} label={r.role} dot={false} /> },
            { key: 'signIn', header: 'Sign-in', secondary: true },
            { key: 'last', header: 'Last seen', render: (r) => formatAgo(secondsSince(r.last, NOW)) },
          ]}
          rows={people}
        />
      </Section>
      <Section title="Agents and tokens" aside={<Button size="sm" icon="plus">New token</Button>}>
        <Table
          caption="Agents and tokens"
          hideCaption
          rowKey={(r) => r.id}
          columns={[
            { key: 'id', header: 'Identity', render: (r) => <StatusPill tone={r.kind === 'Agent' ? 'agent' : 'neutral'} label={r.id} dot={false} /> },
            { key: 'scope', header: 'Can do' },
            { key: 'last', header: 'Last used', secondary: true, render: (r) => formatAgo(secondsSince(r.last, NOW)) },
            { key: 'x', header: 'Actions', align: 'end', render: () => <Button size="sm" variant="ghost">Revoke…</Button> },
          ]}
          rows={tokens}
        />
      </Section>
      <div className="d-grid-2">
        <Card title="Remote access" subtitle="Reach this box from outside your home" aside={<StatusPill tone="neutral" label="Off" />} footer={<Button>Set up…</Button>}>
          <p className="om-hint">Off by default. When on, it uses a private overlay network: no open ports on your router. Exposing an app to the whole internet is a separate request you approve, with an allow-list.</p>
        </Card>
        <Card title="Appearance">
          <ThemeSwitch />
        </Card>
      </div>
    </>
  );
}
