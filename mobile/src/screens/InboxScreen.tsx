// SPDX-License-Identifier: Apache-2.0
// One inbox (contract §12.14, docs/design/IA.md §2.9): open alerts, then this person's notifications.
// The text comes from the hub over HTTPS. A notification never approves anything: one tied to a
// request opens the Approvals tab, where approving needs the owner (and a passkey when required).
import { useNavigation } from '@react-navigation/native';
import { useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { OP } from '../api/client';
import { ApiError, type AlertRecord, type InboxItem, type Severity } from '../api/types';
import { useHubData, useNow } from '../data';
import { actionTitle } from '../lib/approvals';
import { safeHttpUrl } from '../lib/scan';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H1, H2, Loading, Notice, P, Screen, s, type Tone } from '../ui/bits';
import { font, space, useTheme } from '../ui/theme';

const SEVERITY_TONE: Record<Severity, Tone> = { info: 'info', warning: 'warn', critical: 'bad' };

function AlertCard({ a, now, onAck, onFix, canAck, canFix, busy }: {
  a: AlertRecord;
  now: number;
  onAck: () => void;
  onFix: () => void;
  canAck: boolean;
  canFix: boolean;
  busy: boolean;
}) {
  const t = useTheme();
  return (
    <Card testID={`alert-${a.id}`}>
      <View style={s.row}>
        <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold, flexShrink: 1 }}>{a.title}</Text>
        <Badge label={a.severity} tone={SEVERITY_TONE[a.severity] ?? 'neutral'} />
      </View>
      <P small>{a.body}</P>
      <P muted small>
        {a.state === 'acknowledged' ? 'Acknowledged · ' : ''}opened {formatAgo(secondsSince(a.opened_at, now))}
        {a.occurrences && a.occurrences > 1 ? ` · ${a.occurrences} times` : ''}
      </P>
      {(canAck || (canFix && a.fix)) && (
        <View style={s.wrap}>
          {a.fix && canFix && <Button testID={`fix-${a.id}`} label="Ask to fix" disabled={busy} onPress={onFix} />}
          {canAck && a.state === 'open' && <Button testID={`ack-${a.id}`} variant="secondary" label="Acknowledge" disabled={busy} onPress={onAck} />}
        </View>
      )}
    </Card>
  );
}

function ItemRow({ n, now, onOpen }: { n: InboxItem; now: number; onOpen: () => void }) {
  const t = useTheme();
  const unread = !n.read_at;
  return (
    <Pressable
      testID={`ntf-${n.id}`}
      accessibilityRole="button"
      accessibilityLabel={`${unread ? 'Unread. ' : ''}${n.title}. ${n.body}`}
      onPress={onOpen}
      style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
    >
      <Card>
        <View style={s.row}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, flexShrink: 1 }}>
            {unread && <View testID={`unread-${n.id}`} style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: t.accent }} />}
            <Text style={{ color: t.text, fontSize: font.md, fontWeight: unread ? font.bold : font.semibold, flexShrink: 1 }}>{n.title}</Text>
          </View>
          <Badge label={n.topic} tone={SEVERITY_TONE[n.severity] ?? 'neutral'} />
        </View>
        <P small>{n.body}</P>
        <P muted small>
          {formatAgo(secondsSince(n.created_at, now))}
          {n.action_id ? ' · tap to review the request' : ''}
        </P>
      </Card>
    </Pressable>
  );
}

export function InboxScreen() {
  const t = useTheme();
  const now = useNow();
  const nav = useNavigation();
  const { api, features, principal, canRequest } = useSignedIn();
  const { inbox, alerts, hubOffsetMs, loading, reload, unreadCount } = useHubData();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>();
  const hubNow = now + (hubOffsetMs ?? 0);
  const hasInbox = features.has(OP.notifications);
  const canAck = principal?.role === 'owner' || principal?.role === 'adult';
  // §12.14: POST /v1/alerts/{id}/fix is for an owner or an agent; an adult who may request other things may not.
  const canFix = principal?.role === 'owner' || (principal?.kind === 'agent' && canRequest === 'yes');

  async function run(fn: () => Promise<string | undefined>) {
    setBusy(true);
    setMsg(undefined);
    try {
      const text = await fn();
      if (text) setMsg({ text, ok: true });
    } catch (e) {
      setMsg({ text: e instanceof ApiError ? `The hub refused: ${e.message}` : String(e), ok: false });
    } finally {
      await reload();
      setBusy(false);
    }
  }

  async function open(n: InboxItem) {
    if (!n.read_at) await api.markRead(n.id).catch(() => undefined);
    if (n.action_id) nav.navigate('Tabs', { screen: 'Approvals' });
    else {
      const url = safeHttpUrl(n.link);
      if (url?.startsWith('https://')) await Linking.openURL(url);
    }
    await reload();
  }

  if (loading && !inbox && !alerts) return <Loading what="your inbox" />;
  const items = [...(inbox ?? [])].sort((x, y) => Date.parse(y.created_at) - Date.parse(x.created_at));
  const open_ = (alerts ?? []).filter((a) => a.state !== 'resolved');
  return (
    <Screen testID="inbox">
      <H1>Inbox</H1>
      <P muted small>What needs your attention, read from your own box. Tapping a request opens it in Approvals; nothing is approved from here.</P>
      {!hasInbox && (
        <Notice text="This hub has no inbox yet; it comes with the notifications module. Until then the phone alerts you itself while the app is open." />
      )}
      {msg && <Notice tone={msg.ok ? 'ok' : 'bad'} text={msg.text} />}
      {open_.length > 0 && <H2>Open alerts ({open_.length})</H2>}
      {open_.map((a) => (
        <AlertCard
          key={a.id}
          a={a}
          now={hubNow}
          busy={busy}
          canAck={canAck}
          canFix={canFix}
          onAck={() => void run(async () => (await api.ackAlert(a.id), `Acknowledged: ${a.title}.`))}
          onFix={() => void run(async () => `Asked to fix: ${actionTitle(await api.fixAlert(a.id))}. It waits in Approvals.`)}
        />
      ))}
      {hasInbox && (
        <>
          <View style={s.row}>
            <H2>Notifications</H2>
            {unreadCount > 0 && (
              <Pressable testID="read-all" accessibilityRole="button" disabled={busy} onPress={() => void run(async () => (await api.markAllRead(), undefined))}>
                <Text style={{ color: t.accent, fontSize: font.sm, fontWeight: font.semibold, marginTop: space.sm }}>Mark all read</Text>
              </Pressable>
            )}
          </View>
          {items.length === 0 ? <P muted>Nothing here yet.</P> : items.map((n) => <ItemRow key={n.id} n={n} now={hubNow} onOpen={() => void open(n)} />)}
        </>
      )}
    </Screen>
  );
}
