// SPDX-License-Identifier: Apache-2.0
// Agents (CORE-SEC-6 kill switch, §12.6 tokens, §3 actions). Each agent shows what it may do (its token's scopes)
// and what it asked recently. Agents only ever file requests; an owner approves each one in Approvals. The one
// control is the kill switch, owner only, asked twice; the hub refuses every agent while it is on and asks for a
// fresh passkey if it wants one (`step_up_required`). There is no per-agent pause on the hub yet.
import { useState } from 'react';
import { Text, View } from 'react-native';
import { OP } from '../api/client';
import { principalLabel } from '../lib/approvals';
import { requestError } from '../lib/manage';
import { summarizeAgents } from '../lib/people';
import { formatAgo, secondsSince } from '../lib/time';
import { useLoad } from '../lib/useLoad';
import { useHubData } from '../data';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H1, H2, Loading, Notice, P, Row, Screen, StateBadge, s } from '../ui/bits';
import { font, useTheme } from '../ui/theme';

export function AgentsScreen() {
  const t = useTheme();
  const { api, features, principal } = useSignedIn();
  const { actions } = useHubData();
  const sw = useLoad(() => api.killSwitch(), [api]);
  const tokens = useLoad(() => (features.has(OP.tokens) ? api.apiTokens() : Promise.resolve(undefined)).catch(() => undefined), [api, features]);
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' }>();
  if (sw.loading) return <Loading what="agents" />;

  const isOwner = principal?.role === 'owner' && features.has(OP.killSwitchSet);
  const on = !!sw.data?.on;
  const agents = summarizeAgents(actions ?? [], tokens.data);

  async function flip() {
    if (!on && !armed) return setArmed(true);
    setArmed(false);
    setBusy(true);
    setMsg(undefined);
    try {
      await api.setKillSwitch(!on, on ? undefined : 'Stopped from the phone');
      setMsg({ text: on ? 'Agents may work again. Each request still waits for approval.' : 'Every agent is stopped.', tone: 'ok' });
      await sw.reload();
    } catch (e) {
      setMsg({ text: requestError(e, 'changing the kill switch').text, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen testID="agents">
      <H1>Agents</H1>
      <P muted small>AI agents such as Hermes only ask. An owner approves each request in Approvals; nothing an agent asks happens before that.</P>
      <Card testID="kill-switch">
        <View style={s.wrap}>
          <Badge label={on ? 'All agents stopped' : 'Agents allowed to ask'} tone={on ? 'bad' : 'ok'} />
        </View>
        {sw.data?.changed_at ? (
          <P muted small>
            Changed {formatAgo(secondsSince(sw.data.changed_at, Date.now()))}{sw.data.changed_by ? ` by ${principalLabel(sw.data.changed_by)}` : ''}.
          </P>
        ) : null}
        {sw.data?.reason ? <Row label="Reason" value={sw.data.reason} /> : null}
        {isOwner ? (
          <Button
            testID="kill-switch-toggle"
            variant={on ? 'primary' : 'danger'}
            disabled={busy}
            label={on ? 'Let agents work again' : armed ? 'Tap again: stop every agent now' : 'Stop all agents'}
            onPress={() => void flip()}
          />
        ) : (
          <P muted small>Only an owner can stop or restart agents.</P>
        )}
      </Card>
      {msg && <Notice tone={msg.tone} text={msg.text} />}
      <H2>Agents</H2>
      {agents.length === 0 ? <P muted>No agent has asked for anything yet.</P> : null}
      {agents.map((a) => (
        <Card key={a.id} testID={`agent-${a.id}`}>
          <View style={s.row}>
            <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold, flexShrink: 1 }}>{a.id}</Text>
            {a.waiting > 0 ? <Badge label={`${a.waiting} waiting`} tone="warn" /> : null}
          </View>
          <P muted small>
            {a.asks} ask{a.asks === 1 ? '' : 's'}; {a.approved} approved, {a.denied} denied
            {a.last ? `; last ${formatAgo(secondsSince(a.last, Date.now()))}` : ''}
          </P>
          {a.scopes ? <P muted small>May: {a.scopes.length ? a.scopes.join(', ') : 'nothing'}</P> : <P muted small>Scopes are shown to owners when the hub lists tokens.</P>}
          {a.recent.map((r) => (
            <View key={r.id} style={s.row}>
              <Text style={{ color: t.text, fontSize: font.sm, flexShrink: 1 }}>{r.type}{r.params.app_id ? ` ${r.params.app_id}` : ''}</Text>
              <StateBadge state={r.state} />
            </View>
          ))}
        </Card>
      ))}
    </Screen>
  );
}
