// SPDX-License-Identifier: Apache-2.0
// Backups (contract §12.12): is the box protected, where do copies go, what ran last. The two buttons only
// FILE a request (`backup.run`, `backup.verify`, always `approve: false`); an owner approves it in Approvals.
// Restore is not here: it is destructive and always needs a passkey, so it stays on the dashboard.
import { useNavigation } from '@react-navigation/native';
import { useState } from 'react';
import { Text, View } from 'react-native';
import { OP } from '../api/client';
import type { Action, BackupBadge } from '../api/types';
import { useHubData } from '../data';
import { formatBytes, requestError } from '../lib/manage';
import { useLoad } from '../lib/useLoad';
import { formatAgo, secondsSince } from '../lib/time';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H1, H2, Loading, Notice, P, Row, Screen, s, StateBadge, type Tone } from '../ui/bits';
import { font, useTheme } from '../ui/theme';

const HEALTH: Record<string, { label: string; tone: Tone }> = {
  ok: { label: 'Protected', tone: 'ok' },
  stale: { label: 'Out of date', tone: 'warn' },
  failing: { label: 'Failing', tone: 'bad' },
  not_configured: { label: 'Not set up', tone: 'warn' },
};
const BADGE_TONE: Record<string, Tone> = { verified: 'ok', unverified: 'warn', stale: 'warn', failing: 'bad', none: 'neutral' };

function ago(iso: string | null | undefined): string {
  return iso ? formatAgo(secondsSince(iso, Date.now())) : 'never';
}

export function BackupsScreen() {
  const t = useTheme();
  const nav = useNavigation();
  const { api, features, canRequest } = useSignedIn();
  const { actions, reload: reloadHub } = useHubData();
  const status = useLoad(() => api.backupStatus(), [api]);
  const dests = useLoad(() => (features.has(OP.backupDestinations) ? api.backupDestinations() : Promise.resolve([])), [api, features]);
  const runs = useLoad(() => (features.has(OP.backupRuns) ? api.backupRuns() : Promise.resolve([])), [api, features]);
  const [busy, setBusy] = useState(false);
  const [filed, setFiled] = useState<Action>();
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' }>();

  if (status.loading) return <Loading what="backups" />;
  const mayAsk = canRequest !== 'no' && features.has(OP.backupRequestRun);
  // The live state of the request just filed: it moves on once an owner decides.
  const live = filed ? ((actions ?? []).find((a) => a.id === filed.id) ?? filed) : undefined;

  async function file(kind: 'run' | 'verify') {
    setBusy(true);
    setMsg(undefined);
    try {
      const idempotencyKey = uuidv4();
      const a =
        kind === 'run'
          ? await api.requestBackupRun({ reason: 'Requested from the phone', idempotencyKey })
          : await api.requestBackupVerify({ reason: 'Requested from the phone', idempotencyKey });
      setFiled(a);
      setMsg({ text: 'Request sent. No backup has started: it waits in Approvals until an owner decides.', tone: 'ok' });
      await reloadHub();
    } catch (e) {
      setMsg({ text: requestError(e, kind === 'run' ? 'a backup' : 'a backup check').text, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  const d = status.data;
  const h = HEALTH[d?.health ?? ''] ?? { label: d?.health ?? 'Unknown', tone: 'neutral' as Tone };
  const apps = Object.entries(d?.badges?.apps ?? {});
  return (
    <Screen testID="backups">
      <H1>Backups</H1>
      {status.error && !d ? <Notice tone={status.forbidden ? 'warn' : 'bad'} text={status.forbidden ? 'This sign-in may not read backups.' : `Could not read backups: ${status.error.message}`} /> : null}
      {d && (
        <Card>
          <View style={s.wrap}>
            <Badge label={h.label} tone={h.tone} />
            {d.badges?.box ? <Badge label={`box ${d.badges.box.state}`} tone={BADGE_TONE[d.badges.box.state] ?? 'neutral'} /> : null}
          </View>
          <Row label="Last backup" value={ago(d.last_success_at)} />
          <Row label="Last restore check" value={ago(d.last_verified_restore_at)} />
          <Row label="Next run" value={d.next_run_at ? new Date(d.next_run_at).toLocaleString() : 'not scheduled'} />
          <Row label="Copies" value={d.copies ?? 'unknown'} />
          {apps.length > 0 && (
            <View style={s.wrap}>
              {apps.map(([id, b]: [string, BackupBadge]) => (
                <Badge key={id} label={`${id}: ${b.state}`} tone={BADGE_TONE[b.state] ?? 'neutral'} />
              ))}
            </View>
          )}
        </Card>
      )}
      <H2>Destinations</H2>
      {(dests.data ?? []).length === 0 ? (
        <P muted>{dests.forbidden ? 'Only owners and adults can see destinations.' : 'No destination yet. Add one on the dashboard; it needs an owner’s approval.'}</P>
      ) : (
        (dests.data ?? []).map((x) => (
          <Card key={x.id} testID={`dest-${x.id}`}>
            <View style={s.row}>
              <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold }}>{x.label}</Text>
              <Badge label={x.kind} />
            </View>
            <View style={s.wrap}>
              {x.primary ? <Badge label="primary" tone="info" /> : null}
              {x.append_only ? <Badge label="append only" /> : null}
              {x.state ? <Badge label={x.state} tone={x.state === 'online' || x.state === 'ok' ? 'ok' : 'warn'} /> : null}
              {x.free_bytes != null ? <Badge label={`${formatBytes(x.free_bytes)} free`} /> : null}
            </View>
          </Card>
        ))
      )}
      <H2>Recent runs</H2>
      {(runs.data ?? []).length === 0 ? (
        <P muted>No runs yet.</P>
      ) : (
        (runs.data ?? []).slice(0, 5).map((r) => (
          <Card key={r.id} testID={`run-${r.id}`}>
            <View style={s.row}>
              <Text style={{ color: t.text }}>{ago(r.started_at)}</Text>
              <Badge label={r.state} tone={r.state === 'succeeded' ? 'ok' : r.state === 'failed' ? 'bad' : 'info'} />
            </View>
            {r.bytes_total ? <P muted small>{formatBytes(r.bytes_done)} of {formatBytes(r.bytes_total)}</P> : null}
            {r.reason ? <P muted small>{r.reason}</P> : null}
          </Card>
        ))
      )}
      <H2>Ask for a backup</H2>
      {!features.has(OP.backupRequestRun) ? (
        <P muted>This hub cannot take backup requests from the phone yet.</P>
      ) : (
        <>
          <View style={s.wrap}>
            <Button testID="backup-run" label={busy ? 'Sending…' : 'Back up now'} disabled={busy || !mayAsk} onPress={() => void file('run')} />
            <Button testID="backup-verify" variant="secondary" label="Check latest backup" disabled={busy || !mayAsk} onPress={() => void file('verify')} />
          </View>
          {canRequest === 'no' && <Notice tone="warn" text="Only an owner (or an agent) can ask for a backup." />}
        </>
      )}
      {msg && <Notice tone={msg.tone} text={msg.text} />}
      {live && (
        <View style={s.wrap}>
          <StateBadge state={live.state} />
          <Button variant="secondary" label="Open Approvals" onPress={() => nav.navigate('Tabs', { screen: 'Approvals' })} />
        </View>
      )}
      <P muted small>A restore can overwrite what is on the box, so it always needs an owner's passkey on the dashboard.</P>
    </Screen>
  );
}
