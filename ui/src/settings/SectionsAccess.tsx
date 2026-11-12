// SPDX-License-Identifier: Apache-2.0
// Settings sections about who can do what: Account & security, Users & roles, Agents & MCP.
import { useState } from 'react';
import { formatAgo, formatDay, secondsSince } from '../lib/time';
import { Button } from '../components/Button';
import { Dialog } from '../components/Dialog';
import { StatusPill } from '../components/StatusPill';
import { TOKEN_STATE, tokenState } from './logic';
import { Async, CallHint, Empty, Group, Row, Rows, SectionHead, SetIcon, Switch } from './primitives';
import type { AccountData, AgentsData, Loadable, OnIntent, Person, TokenKind } from './types';

export interface SectionProps<T> {
  data: Loadable<T>;
  /** The hub's clock (ms epoch). */
  now: number;
  onIntent: OnIntent;
  onRetry?: () => void;
}

const ago = (iso: string | null, now: number) => (iso ? formatAgo(secondsSince(iso, now)) : 'never');
const TOKEN_KIND: Record<TokenKind, string> = { pat: 'Person', agt: 'Agent', plg: 'Plugin', nod: 'Node', aut: 'Automation' };
const PAUSED = 'Changes are paused while the hub is not answering.';

/* ---------- Account & security ---------- */
export function AccountSection({ data, now, onIntent, onRetry }: SectionProps<AccountData>) {
  return (
    <>
      <SectionHead icon="lock" title="Account & security" lede="How you sign in, where you are signed in, and the tokens that can act for you." />
      <Async value={data} label="your account" now={now} onRetry={onRetry} rows={5}>
        {(d, live) => (
          <>
            <Group
              title="Passkeys"
              description="A passkey on your phone or laptop is how you sign in and how you approve requests. Nothing to remember, nothing to phish."
              aside={
                <Button size="sm" icon="plus" disabled={!live || !d.passkeysAvailable} onClick={() => onIntent({ type: 'auth.passkey.register', params: {}, mode: 'instant', title: 'Add a passkey', call: 'POST /v1/auth/passkeys/register/options' })}>
                  Add a passkey
                </Button>
              }
            >
              {!d.passkeysAvailable ? (
                <p className="om-note om-tone-info">
                  Passkeys arrive with the next gateway release (CORE-SEC-2). Until then you sign in with your owner token, and approvals are recorded as “token” in Activity.
                </p>
              ) : d.passkeys.length === 0 ? (
                <Empty icon="lock" title="No passkey yet" command="onemind auth passkey add">
                  Add one now: without a passkey, anyone holding your token can approve requests.
                </Empty>
              ) : (
                <Rows label="Passkeys">
                  {d.passkeys.map((p) => (
                    <Row key={p.id} icon="key" title={p.name} description={`Added ${formatDay(p.created_at)} · last used ${ago(p.last_used_at, now)}`} />
                  ))}
                </Rows>
              )}
              <Rows label="Sign-in options">
                <Row
                  icon="clock"
                  title="Authenticator app codes"
                  description="A fallback when no passkey device is near. Turning it on is a request you approve."
                  trailing={<Switch checked={d.totp} label="Authenticator app codes" disabled={!live} onToggle={() => onIntent({ type: 'auth.totp.set', params: { enabled: !d.totp }, mode: 'request', title: d.totp ? 'Turn off authenticator codes' : 'Turn on authenticator codes', call: 'PUT /v1/auth/totp' })} />}
                />
                <Row
                  icon="approvals"
                  title="Require a passkey to approve"
                  description="Every approval is a passkey signature over the exact plan. Off means a signed-in session alone can approve."
                  trailing={
                    <Switch
                      checked={d.requirePasskeyApproval}
                      label="Require a passkey to approve"
                      disabled={!live}
                      onToggle={() => onIntent({ type: 'auth.policy.set', params: { require_passkey_approval: !d.requirePasskeyApproval }, mode: 'request', title: 'Change the approval rule', call: 'PUT /v1/auth/policy' })}
                    />
                  }
                />
              </Rows>
            </Group>

            <Group
              title={`Sessions (${d.sessions.length})`}
              description="Every browser, phone and terminal signed in as you. Signing out takes effect at once."
              aside={
                d.sessions.length > 1 && (
                  <Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'auth.sessions.revoke_others', params: {}, mode: 'instant', title: 'Signed out everywhere else', call: 'DELETE /v1/auth/sessions?except=current' })}>
                    Sign out everywhere else
                  </Button>
                )
              }
            >
              {d.sessions.length === 0 ? (
                <Empty icon="user" title="No other sessions">Only this browser is signed in.</Empty>
              ) : (
                <Rows label="Sessions">
                  {d.sessions.map((s) => (
                    <Row
                      key={s.id}
                      icon={s.client === 'cli' ? 'hash' : s.client === 'phone' ? 'nodes' : 'globe'}
                      title={
                        <>
                          {s.device} {s.current && <StatusPill tone="ok" label="This device" dot={false} />}
                        </>
                      }
                      description={`Active ${ago(s.last_seen_at, now)} · signed in ${formatDay(s.created_at)}`}
                      meta={s.approval === 'token' ? 'Approves with a token (no passkey)' : 'Approves with a passkey'}
                      trailing={
                        !s.current && (
                          <Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'auth.session.revoke', params: { id: s.id }, mode: 'instant', title: `Signed out ${s.device}`, call: `DELETE /v1/auth/sessions/${s.id}` })}>
                            Sign out
                          </Button>
                        )
                      }
                    />
                  ))}
                </Rows>
              )}
            </Group>

            <Group
              title="Tokens"
              description="For scripts, the CLI and devices. Shown once when created; prefixed om_ so leak scanners catch them."
              aside={
                <Button size="sm" icon="plus" disabled={!live} onClick={() => onIntent({ type: 'token.create', params: { kind: 'pat', expires: '30d' }, mode: 'request', title: 'Create a personal token', call: 'onemind tokens create --kind pat --expires 30d' })}>
                  New token
                </Button>
              }
            >
              {d.tokens.length === 0 ? (
                <Empty icon="lock" title="No tokens" command="onemind tokens create --kind pat --expires 30d">
                  You have not created any. The CLI signs in with your passkey instead.
                </Empty>
              ) : (
                <Rows label="Tokens">
                  {d.tokens.map((t) => {
                    const st = tokenState(t, now);
                    const dead = st === 'revoked' || st === 'expired';
                    return (
                      <Row
                        key={t.id}
                        icon="key"
                        tone={t.kind === 'agt' ? 'agent' : undefined}
                        title={
                          <>
                            {t.name} <StatusPill tone={TOKEN_STATE[st].tone} label={TOKEN_STATE[st].label} />
                          </>
                        }
                        description={`${TOKEN_KIND[t.kind]} · ${t.principal} · ${t.expires_at ? `expires ${formatDay(t.expires_at)}` : 'no expiry'}`}
                        meta={`Last used ${ago(t.last_used_at, now)} · ${t.id}`}
                        trailing={
                          !dead && (
                            <span className="om-set-actions">
                              <Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'token.rotate', params: { id: t.id }, mode: 'instant', title: `Rotated ${t.name}`, call: `onemind tokens rotate ${t.id}` })}>
                                Rotate
                              </Button>
                              <Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'token.revoke', params: { id: t.id }, mode: 'instant', title: `Revoked ${t.name}`, call: `DELETE /v1/tokens/${t.id}` })}>
                                Revoke
                              </Button>
                            </span>
                          )
                        }
                      />
                    );
                  })}
                </Rows>
              )}
            </Group>
            {!live && <p className="om-hint">{PAUSED}</p>}
          </>
        )}
      </Async>
      <CallHint calls={['GET /v1/auth/sessions', 'DELETE /v1/auth/sessions/{id}', 'onemind tokens list', 'onemind tokens create --kind pat --expires 30d', 'onemind tokens rotate <id>', 'DELETE /v1/tokens/{id}']} />
    </>
  );
}

/* ---------- Users & roles ---------- */
const ROLE_LABEL: Record<Person['role'], string> = { owner: 'Owner', adult: 'Adult', guest: 'Guest' };
const MATRIX: Array<[string, boolean, boolean, boolean]> = [
  ['Approve requests', true, false, false],
  ['Ask for installs, updates and restores', true, true, false],
  ['Open apps shared with them', true, true, true],
  ['See Activity and Alerts', true, true, false],
  ['Manage people, agents and tokens', true, false, false],
];

export function UsersSection({ data, now, onIntent, onRetry }: SectionProps<Person[]>) {
  return (
    <>
      <SectionHead icon="users" title="Users & roles" lede="Everyone who can sign in to this box. Only the owner approves; adults can ask; guests only open apps shared with them." />
      <Async
        value={data}
        label="people"
        now={now}
        onRetry={onRetry}
        isEmpty={(d) => d.length === 0}
        empty={
          <Empty icon="users" title="Only you so far" command="onemind people invite --role adult">
            Invite family or housemates. Each person gets their own sign-in and their own Home.
          </Empty>
        }
      >
        {(d, live) => (
          <Group
            title={`People (${d.length})`}
            aside={
              <Button size="sm" icon="plus" disabled={!live} onClick={() => onIntent({ type: 'person.invite', params: { role: 'adult' }, mode: 'request', title: 'Invite a person', call: 'onemind people invite --role adult' })}>
                Invite
              </Button>
            }
          >
            <Rows label="People">
              {d.map((p) => (
                <Row
                  key={p.id}
                  icon="user"
                  title={
                    <>
                      {p.name} <StatusPill tone={p.role === 'owner' ? 'info' : 'neutral'} label={ROLE_LABEL[p.role]} dot={false} />
                    </>
                  }
                  description={p.signIn === 'invited' ? 'Invitation sent, not accepted yet' : `Signs in with ${p.signIn === 'passkey' ? 'a passkey' : 'authenticator codes'} · seen ${ago(p.last_seen_at, now)}`}
                  trailing={
                    p.role !== 'owner' && (
                      <Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'person.role.set', params: { id: p.id, role: p.role === 'adult' ? 'guest' : 'adult' }, mode: 'request', title: `Make ${p.name} ${p.role === 'adult' ? 'a guest' : 'an adult'}`, call: `PUT /v1/people/${p.id}` })}>
                        Make {p.role === 'adult' ? 'guest' : 'adult'}
                      </Button>
                    )
                  }
                />
              ))}
            </Rows>
          </Group>
        )}
      </Async>
      <Group title="What each role can do">
        <div className="om-table-wrap">
          <table className="om-table om-set-matrix">
            <caption className="om-visually-hidden">What each role can do</caption>
            <thead>
              <tr>
                <th scope="col">Permission</th>
                <th scope="col">Owner</th>
                <th scope="col">Adult</th>
                <th scope="col">Guest</th>
              </tr>
            </thead>
            <tbody>
              {MATRIX.map(([what, ...can]) => (
                <tr key={what}>
                  <th scope="row">{what}</th>
                  {can.map((c, i) => (
                    <td key={i} data-label={['Owner', 'Adult', 'Guest'][i]}>
                      {c ? <StatusPill tone="ok" label="Yes" /> : <StatusPill tone="neutral" label="No" dot={false} />}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="om-hint">Agents are not people: they have their own principals under Agents &amp; MCP and can only ask.</p>
      </Group>
      <CallHint calls={['GET /v1/people', 'onemind people invite --role adult|guest', 'PUT /v1/people/{id}   (a request the owner approves)']} />
    </>
  );
}

/* ---------- Agents & MCP ---------- */
export function AgentsSection({ data, now, onIntent, onRetry, approvalsHref = '#/approvals' }: SectionProps<AgentsData> & { approvalsHref?: string }) {
  const [confirm, setConfirm] = useState(false);
  const [typed, setTyped] = useState('');
  const close = () => {
    setConfirm(false);
    setTyped('');
  };
  return (
    <>
      <SectionHead icon="agent" title="Agents & MCP" lede="AI agents have their own identity. They can read what you allow and ask for actions; every action waits for you." />
      <Async
        value={data}
        label="agents"
        now={now}
        onRetry={onRetry}
        rows={4}
      >
        {(d, live) => {
          const active = d.agents.filter((a) => a.state === 'active');
          return (
            <>
              <Group
                title="Model Context Protocol (MCP)"
                description="Agents connect here with their own token. Tools that change something only create requests."
                aside={<StatusPill tone={d.mcp.enabled ? 'ok' : 'neutral'} label={d.mcp.enabled ? 'On' : 'Off'} />}
              >
                <Rows label="MCP server">
                  <Row icon="link" title="Endpoint" description={<code>{d.mcp.path}</code>} meta="On this box only, behind the gateway login. Not reachable from the internet." />
                </Rows>
              </Group>
              <Group
                title={`Agents (${d.agents.length})`}
                aside={
                  <Button size="sm" variant="danger" disabled={!live || active.length === 0} onClick={() => setConfirm(true)}>
                    <SetIcon name="pause" size={18} />
                    Revoke all
                  </Button>
                }
              >
                {d.agents.length === 0 ? (
                  <Empty icon="agent" title="No agents connected" command="onemind tokens create --kind agent --name my-agent --expires 30d">
                    Create an agent token, then give it to the agent. It can ask for actions; you approve each one.
                  </Empty>
                ) : (
                  <ul className="om-set-cards" aria-label="Agents">
                    {d.agents.map((a) => (
                      <li key={a.id} className="om-set-agent">
                        <div className="om-set-agent-head">
                          <span className="om-set-row-icon om-tone-agent">
                            <SetIcon name="agent" size={18} />
                          </span>
                          <div className="om-set-row-main">
                            <div className="om-set-row-title">
                              {a.name} <StatusPill tone={a.state === 'active' ? 'agent' : 'neutral'} label={a.state === 'active' ? 'Active' : 'Suspended'} />
                            </div>
                            <div className="om-set-meta">
                              {a.id} · {a.tokens} token{a.tokens === 1 ? '' : 's'} · active {ago(a.last_active_at, now)}
                            </div>
                          </div>
                          {a.state === 'active' ? (
                            <Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'agent.suspend', params: { id: a.id }, mode: 'instant', title: `Suspended ${a.name}`, call: `POST /v1/agents/${a.id}/suspend` })}>
                              Suspend
                            </Button>
                          ) : (
                            <Button size="sm" disabled={!live} onClick={() => onIntent({ type: 'agent.resume', params: { id: a.id }, mode: 'request', title: `Resume ${a.name}`, call: `POST /v1/agents/${a.id}/resume` })}>
                              Request resume
                            </Button>
                          )}
                        </div>
                        <div className="om-set-tools" aria-label={`${a.name} tools`} role="group">
                          {a.tools.map((t) => (
                            <span key={t.name} className="om-set-tool" data-kind={t.kind}>
                              <code>{t.name}</code>
                              <span className="om-visually-hidden">{t.kind === 'read' ? ' (reads)' : ' (asks; you approve)'}</span>
                            </span>
                          ))}
                        </div>
                        <dl className="om-set-agent-stats">
                          <div>
                            <dt>Asked this week</dt>
                            <dd>{a.week.asked}</dd>
                          </div>
                          <div>
                            <dt>You approved</dt>
                            <dd>{a.week.approved}</dd>
                          </div>
                          <div>
                            <dt>You denied</dt>
                            <dd>{a.week.denied}</dd>
                          </div>
                          <div>
                            <dt>Waiting</dt>
                            <dd>{a.pending > 0 ? <a href={approvalsHref}>{a.pending}</a> : 0}</dd>
                          </div>
                        </dl>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="om-hint">
                  <span className="om-set-tool" data-kind="read">
                    <code>read</code>
                  </span>{' '}
                  tools only look.{' '}
                  <span className="om-set-tool" data-kind="request">
                    <code>request</code>
                  </span>{' '}
                  tools create a request in Approvals. Reducing an agent's power is instant; giving it back is a request.
                </p>
              </Group>
              <Dialog
                open={confirm}
                onClose={close}
                role="alertdialog"
                title="Revoke all agent access?"
                description={`All ${active.length} active agents are suspended now: their tokens stop working and their ${active.reduce((n, a) => n + a.pending, 0)} waiting requests are cancelled. Resuming each one is a request you approve.`}
                actions={
                  <>
                    <Button onClick={close}>Keep access</Button>
                    <Button
                      variant="danger"
                      disabled={typed.trim().toUpperCase() !== 'REVOKE'}
                      onClick={() => {
                        onIntent({ type: 'agents.suspend_all', params: {}, mode: 'instant', title: 'Suspended every agent', call: 'POST /v1/agents/suspend-all' });
                        close();
                      }}
                    >
                      Revoke all
                    </Button>
                  </>
                }
              >
                <label className="om-set-field">
                  Type REVOKE to confirm
                  <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} />
                </label>
              </Dialog>
            </>
          );
        }}
      </Async>
      <CallHint calls={['GET /v1/agents', 'POST /v1/agents/{id}/suspend   (instant)', 'POST /v1/agents/{id}/resume    (a request you approve)', 'onemind tokens create --kind agent --name <name> --expires 30d']} />
    </>
  );
}

