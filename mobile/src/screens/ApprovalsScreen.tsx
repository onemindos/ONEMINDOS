// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react';
import { Text, View } from 'react-native';
import type { Action } from '../api/types';
import { useHubData, useNow } from '../data';
import { actionTitle, decide, isPending, sortByRecent, type Decision } from '../lib/approvals';
import { formatAgo, formatIn, secondsSince } from '../lib/time';
import { useSignedIn, type Ability } from '../session';
import { Button, Card, H1, KindBadge, Loading, Notice, P, Row, Screen, s } from '../ui/bits';
import { space, useTheme } from '../ui/theme';

/** The exact request, as the hub stores it: what is approved is what runs. */
export function exactParams(a: Action): string {
  return JSON.stringify({ type: a.type, params: a.params }, null, 2);
}

function PendingCard({
  a,
  now,
  canDecide,
  busy,
  onDecide,
}: {
  a: Action;
  now: number;
  canDecide: Ability;
  busy: boolean;
  onDecide: (a: Action, d: Decision) => void;
}) {
  const t = useTheme();
  const expired = Date.parse(a.expires_at) <= now;
  const off = busy || canDecide === 'no' || expired;
  return (
    <Card testID={`pending-${a.id}`}>
      <View style={s.row}>
        <Text style={{ color: t.text, fontSize: 17, fontWeight: '600', flexShrink: 1 }}>{actionTitle(a)}</Text>
        <KindBadge kind={a.requested_by?.kind} />
      </View>
      <Row label="Requested by" value={a.requested_by ? `${a.requested_by.kind}: ${a.requested_by.id}` : 'unknown'} />
      <Row label="Asked" value={formatAgo(secondsSince(a.created_at ?? '', now))} />
      <Row label="Expires" value={formatIn(a.expires_at, now)} />
      <View style={{ backgroundColor: t.neutralBg, borderRadius: 8, padding: space.md }}>
        <Text style={{ color: t.muted, fontSize: 12, marginBottom: 4 }}>Exact request</Text>
        <Text testID={`params-${a.id}`} style={{ color: t.text, fontFamily: 'Courier', fontSize: 13 }}>
          {exactParams(a)}
        </Text>
      </View>
      {a.requested_by?.kind === 'agent' && (
        <P muted small>An AI agent asked for this. It cannot approve its own request.</P>
      )}
      <View style={s.wrap}>
        <Button testID={`approve-${a.id}`} label="Approve" disabled={off} onPress={() => onDecide(a, 'approve')} />
        <Button testID={`deny-${a.id}`} label="Deny" variant="danger" disabled={off} onPress={() => onDecide(a, 'deny')} />
      </View>
    </Card>
  );
}

export function ApprovalsScreen() {
  const now = useNow();
  const { api, canDecide, markForbidden } = useSignedIn();
  const { actions, hubOffsetMs, loading, reload } = useHubData();
  const [busy, setBusy] = useState<string>();
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>();
  const hubNow = now + (hubOffsetMs ?? 0);

  async function onDecide(a: Action, d: Decision) {
    setBusy(a.id);
    setMsg(undefined);
    const r = await decide(api, a, d);
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
      {msg && <Notice tone={msg.ok ? 'ok' : 'bad'} text={msg.text} />}
      {pending.length === 0 ? (
        <P muted>Nothing is waiting.</P>
      ) : (
        pending.map((a) => (
          <PendingCard key={a.id} a={a} now={hubNow} canDecide={canDecide} busy={busy !== undefined} onDecide={(x, d) => void onDecide(x, d)} />
        ))
      )}
    </Screen>
  );
}
