// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react';
import { Text, View } from 'react-native';
import type { Action, Risk } from '../api/types';
import { useHubData, useNow } from '../data';
import { actionTitle, decide, isPending, needsPasskey, RISK_LABEL, sortByRecent, type Decision, type StepUp } from '../lib/approvals';
import { platformPasskeys } from '../lib/passkeys';
import { formatAgo, formatIn, secondsSince } from '../lib/time';
import { useSignedIn, type Ability } from '../session';
import { Badge, Button, Card, H1, KindBadge, Loading, Notice, P, Row, Screen, s, type Tone } from '../ui/bits';
import { space, useTheme } from '../ui/theme';

const RISK_TONE: Record<Risk, Tone> = { read: 'neutral', write: 'info', sensitive: 'warn', destructive: 'bad', actuate: 'bad' };

/** `sha256:9a1e5c…8f7a`: enough to compare with the dashboard or CLI, short enough to read. */
export function shortHash(h: string | null | undefined): string | undefined {
  if (!h) return undefined;
  const [alg, hex] = h.includes(':') ? h.split(':', 2) : ['sha256', h];
  return hex && hex.length > 14 ? `${alg}:${hex.slice(0, 6)}…${hex.slice(-4)}` : h;
}

function List({ label, items }: { label: string; items: unknown[] | undefined }) {
  const t = useTheme();
  if (!items?.length) return null;
  return (
    <View style={{ gap: 2 }}>
      <Text style={{ color: t.muted, fontSize: 12 }}>{label}</Text>
      {items.slice(0, 8).map((x, i) => (
        <Text key={i} style={{ color: t.text, fontSize: 13 }}>
          • {typeof x === 'string' ? x : JSON.stringify(x)}
        </Text>
      ))}
      {items.length > 8 && <Text style={{ color: t.muted, fontSize: 12 }}>and {items.length - 8} more</Text>}
    </View>
  );
}

/** §12.4 plan: what will actually run. The approval is bound to its hash. */
function PlanBlock({ a }: { a: Action }) {
  const t = useTheme();
  const p = a.plan;
  if (!p) return null;
  return (
    <View testID={`plan-${a.id}`} style={{ gap: space.sm, borderTopWidth: 1, borderTopColor: t.border, paddingTop: space.sm }}>
      <Text style={{ color: t.text, fontWeight: '600' }}>What will happen</Text>
      {p.summary ? <P small>{p.summary}</P> : null}
      <List label="Images" items={p.images} />
      <List label="Storage" items={p.volumes} />
      <List label="Machines" items={p.nodes} />
      <List label="Objects" items={p.objects} />
      {p.warnings?.map((w, i) => <Notice key={i} tone="warn" text={w} />)}
      {a.plan_sha256 ? <Row label="Plan" value={shortHash(a.plan_sha256)} /> : null}
    </View>
  );
}

/** The requester's own words. From an agent this is untrusted text, so it is labelled as such. */
function ReasonBlock({ a }: { a: Action }) {
  const t = useTheme();
  if (!a.reason) return null;
  const agent = a.requested_by?.kind === 'agent';
  return (
    <View testID={`reason-${a.id}`} style={{ backgroundColor: agent ? t.agentBg : t.neutralBg, borderRadius: 8, padding: space.md, gap: 4 }}>
      <Text style={{ color: agent ? t.agent : t.muted, fontSize: 12, fontWeight: '600' }}>
        {agent ? 'Reason given by the agent (its words, not checked by the hub)' : 'Reason given'}
      </Text>
      <Text style={{ color: t.text, fontSize: 14 }}>{a.reason}</Text>
    </View>
  );
}

/** The exact request, as the hub stores it: what is approved is what runs. */
export function exactParams(a: Action): string {
  return JSON.stringify({ type: a.type, params: a.params }, null, 2);
}

function PendingCard({
  a,
  now,
  canDecide,
  busy,
  offline,
  passkey,
  onDecide,
}: {
  a: Action;
  now: number;
  canDecide: Ability;
  busy: boolean;
  offline: boolean;
  passkey: boolean;
  onDecide: (a: Action, d: Decision) => void;
}) {
  const t = useTheme();
  const expired = Date.parse(a.expires_at) <= now;
  const off = busy || canDecide === 'no' || expired || offline;
  return (
    <Card testID={`pending-${a.id}`}>
      <View style={s.row}>
        <Text style={{ color: t.text, fontSize: 17, fontWeight: '600', flexShrink: 1 }}>{actionTitle(a)}</Text>
        <KindBadge kind={a.requested_by?.kind} />
      </View>
      {a.risk && <Badge label={RISK_LABEL[a.risk] ?? a.risk} tone={RISK_TONE[a.risk] ?? 'neutral'} />}
      <Row label="Requested by" value={a.requested_by ? `${a.requested_by.kind}: ${a.requested_by.id}` : 'unknown'} />
      <Row label="Asked" value={formatAgo(secondsSince(a.created_at ?? '', now))} />
      <Row label="Expires" value={formatIn(a.expires_at, now)} />
      <View style={{ backgroundColor: t.neutralBg, borderRadius: 8, padding: space.md }}>
        <Text style={{ color: t.muted, fontSize: 12, marginBottom: 4 }}>Exact request</Text>
        <Text testID={`params-${a.id}`} style={{ color: t.text, fontFamily: 'Courier', fontSize: 13 }}>
          {exactParams(a)}
        </Text>
      </View>
      <ReasonBlock a={a} />
      <PlanBlock a={a} />
      {a.requested_by?.kind === 'agent' && (
        <P muted small>An AI agent asked for this. It cannot approve its own request.</P>
      )}
      {passkey && canDecide !== 'no' && <P muted small>Approving asks for Face ID, your fingerprint or your screen lock.</P>}
      <View style={s.wrap}>
        <Button testID={`approve-${a.id}`} label="Approve" disabled={off} onPress={() => onDecide(a, 'approve')} />
        <Button testID={`deny-${a.id}`} label="Deny" variant="danger" disabled={off} onPress={() => onDecide(a, 'deny')} />
      </View>
    </Card>
  );
}

export function ApprovalsScreen() {
  const now = useNow();
  const { api, canDecide, markForbidden, features, me, connection } = useSignedIn();
  const { actions, hubOffsetMs, loading, reload, error } = useHubData();
  const [busy, setBusy] = useState<string>();
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>();
  const hubNow = now + (hubOffsetMs ?? 0);
  const ownerHasPasskey = (me?.passkeys ?? 0) > 0;
  const ctx: StepUp = {
    features,
    passkeys: platformPasskeys(),
    ownerHasPasskey,
    hubUrl: connection.mode === 'live' ? connection.hubUrl : undefined,
  };

  async function onDecide(a: Action, d: Decision) {
    setBusy(a.id);
    setMsg(undefined);
    const r = await decide(api, a, d, ctx);
    if (!r.ok && r.forbidden) markForbidden();
    setMsg({ text: r.message, ok: r.ok });
    await reload();
    setBusy(undefined);
  }

  if (loading && !actions) return <Loading what="requests" />;
  const pending = sortByRecent((actions ?? []).filter(isPending));
  return (
    <Screen testID="approvals">
      <H1>Approvals</H1>
      <P muted small>Every change waits here. AI agents can ask, but only an owner can say yes.</P>
      {canDecide === 'no' && <Notice tone="warn" text="You can see requests, but only an owner can approve or deny them." />}
      {canDecide === 'unknown' && <Notice text="The hub checks that you are an owner when you approve or deny." />}
      {error && <Notice tone="warn" text="Not connected to the hub right now, so approving and denying are off. They come back when the hub answers." />}
      {msg && <Notice tone={msg.ok ? 'ok' : 'bad'} text={msg.text} />}
      {pending.length === 0 ? (
        <P muted>Nothing is waiting.</P>
      ) : (
        pending.map((a) => (
          <PendingCard
            key={a.id}
            a={a}
            now={hubNow}
            canDecide={canDecide}
            busy={busy !== undefined}
            offline={!!error}
            passkey={needsPasskey(a, ownerHasPasskey)}
            onDecide={(x, d) => void onDecide(x, d)}
          />
        ))
      )}
    </Screen>
  );
}
