// SPDX-License-Identifier: Apache-2.0
// Migration from another cluster: the plans and where each one stands. Read only on the phone. A copy or a
// cutover needs a kubeconfig, which is a credential, so it never goes through a phone; use the dashboard or CLI.
import { Text, View } from 'react-native';
import { formatAgo, secondsSince } from '../lib/time';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Badge, Card, H1, Loading, Notice, P, Screen, s, type Tone } from '../ui/bits';
import { font, useTheme } from '../ui/theme';

const TONE: Record<string, Tone> = { planned: 'info', staged: 'info', running: 'warn', switched: 'ok', superseded: 'neutral' };

export function MigrateScreen() {
  const t = useTheme();
  const { api } = useSignedIn();
  const plans = useLoad(() => api.migratePlans(), [api]);
  if (plans.loading) return <Loading what="migration plans" />;
  return (
    <Screen testID="migrate">
      <H1>Migration</H1>
      {plans.error ? <Notice tone={plans.forbidden ? 'warn' : 'bad'} text={plans.forbidden ? 'Only an owner can see migration plans.' : `Could not read plans: ${plans.error.message}`} /> : null}
      {(plans.data ?? []).length === 0 && !plans.error ? <P muted>No migration has been planned.</P> : null}
      {(plans.data ?? []).map((p) => (
        <Card key={p.id} testID={`plan-${p.id}`}>
          <View style={s.row}>
            <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold }}>{p.name ?? p.app_id ?? p.id}</Text>
            <Badge label={p.state} tone={TONE[p.state] ?? 'neutral'} />
          </View>
          <P muted small>
            {p.namespace ? `from namespace ${p.namespace}` : ''}
            {p.updated_at ? `; updated ${formatAgo(secondsSince(p.updated_at, Date.now()))}` : ''}
          </P>
          {p.last_error ? <Notice tone="bad" text={p.last_error} /> : null}
        </Card>
      ))}
      <P muted small>
        Copying data and switching over need a kubeconfig. That is a credential, so it is never typed into a phone. Use the
        dashboard or the CLI; each step there still waits for an owner's approval.
      </P>
    </Screen>
  );
}
