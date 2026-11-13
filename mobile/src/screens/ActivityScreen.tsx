// SPDX-License-Identifier: Apache-2.0
import { Text, View } from 'react-native';
import { useHubData, useNow } from '../data';
import { actionTitle, sortByRecent } from '../lib/approvals';
import { formatAgo, secondsSince } from '../lib/time';
import { Card, H1, KindBadge, Loading, P, Row, Screen, StateBadge, s } from '../ui/bits';
import { useTheme } from '../ui/theme';

/** §12.4 `approval`: how the owner's yes was given. F-12: a yes without a passkey is labelled as such. */
export const APPROVAL_LABEL: Record<string, string> = {
  passkey: 'with a passkey',
  token: 'without a passkey',
  policy: 'by a standing approval',
  console: 'at the box console',
};

export function ActivityScreen() {
  const t = useTheme();
  const now = useNow();
  const { actions, hubOffsetMs, loading } = useHubData();
  if (loading && !actions) return <Loading what="activity" />;
  const hubNow = now + (hubOffsetMs ?? 0);
  const list = sortByRecent(actions ?? []);
  return (
    <Screen testID="activity">
      <H1>Activity</H1>
      <P muted small>
        Every request and decision, newest first. The hub also keeps a hash-chained audit log; v0 does not serve it over the
        API yet, so this list shows actions only.
      </P>
      {list.length === 0 && <P muted>Nothing has happened yet.</P>}
      {list.map((a) => (
        <Card key={a.id} testID={`activity-${a.id}`}>
          <View style={s.row}>
            <Text style={{ color: t.text, fontSize: 16, fontWeight: '600', flexShrink: 1 }}>{actionTitle(a)}</Text>
            <StateBadge state={a.state} />
          </View>
          <View style={s.wrap}>
            <KindBadge kind={a.requested_by?.kind} />
            <P muted small>
              {a.requested_by?.id ?? 'unknown'} · {formatAgo(secondsSince(a.updated_at ?? a.created_at ?? '', hubNow))}
            </P>
          </View>
          {a.decided_by && <Row label="Decided by" value={`${a.decided_by.kind}: ${a.decided_by.id}`} />}
          {a.approval && <Row label="Approved" value={APPROVAL_LABEL[a.approval] ?? a.approval} />}
          {a.result?.message && <Row label="Result" value={a.result.message} />}
          <Row label="Action id" value={a.id} />
        </Card>
      ))}
    </Screen>
  );
}
