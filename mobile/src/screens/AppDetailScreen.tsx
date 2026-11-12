// SPDX-License-Identifier: Apache-2.0
import { useNavigation, useRoute, type RouteProp } from '@react-navigation/native';
import { useState } from 'react';
import { Text, View } from 'react-native';
import { ApiError, type ActionType } from '../api/types';
import { useHubData } from '../data';
import { principalLabel, requestAction } from '../lib/approvals';
import { installBlockReason } from '../lib/scan';
import type { RootParams } from '../nav';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H1, LinkChip, Notice, P, Row, Screen, s } from '../ui/bits';
import { useTheme } from '../ui/theme';
import { scanLabel, TIER_TONE } from './AppsScreen';

export function AppDetailScreen() {
  const t = useTheme();
  const nav = useNavigation();
  const { params } = useRoute<RouteProp<RootParams, 'AppDetail'>>();
  const { api, canRequest } = useSignedIn();
  const { apps, actions, hubOffsetMs, reload } = useHubData();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' }>();
  const app = apps?.find((a) => a.id === params.id);
  if (!app)
    return (
      <Screen>
        <P muted>This app is not in the hub's catalog.</P>
      </Screen>
    );

  const waiting = (actions ?? []).find((a) => a.state === 'awaiting_approval' && a.params.app_id === app.id);
  const type: ActionType = app.installed ? 'app.remove' : 'app.install';
  const blockReason = type === 'app.install' ? installBlockReason(app, Date.now() + (hubOffsetMs ?? 0)) : undefined;
  const reason =
    canRequest === 'no'
      ? 'Only an owner (or an agent) can ask for changes.'
      : waiting
        ? `A request is already waiting for approval (from ${principalLabel(waiting.requested_by)}).`
        : blockReason;
  const scan = scanLabel(app);

  async function ask() {
    setBusy(true);
    setMsg(undefined);
    try {
      await requestAction(api, type, app!.id);
      setMsg({ text: 'Request sent. It waits in Approvals until an owner decides.', tone: 'ok' });
      await reload();
    } catch (e) {
      setMsg({ text: `Could not send the request: ${e instanceof ApiError ? e.message : String(e)}`, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen testID="app-detail">
      <View>
        <H1>{app.name}</H1>
        <P muted>{app.description}</P>
      </View>
      <View style={s.wrap}>
        <Badge label={app.tier ?? 'no tier'} tone={app.tier ? TIER_TONE[app.tier] : 'warn'} />
        <Badge label={scan.text} tone={scan.tone} />
        {app.installed && <Badge label={app.status.replace(/_/g, ' ')} tone="info" />}
      </View>
      <Card>
        <Row label="Version" value={app.version} />
        <Row label="Licence" value={app.license} />
        <Row label="Category" value={app.category} />
        <Row label="Runs on" value={app.archs.join(', ')} />
        <Row
          label="Needs"
          value={`${app.requires.minMemoryMb ? `${app.requires.minMemoryMb} MB memory` : 'no stated memory'}${app.requires.gpu ? ', a GPU' : ''}`}
        />
        <Row label="Web port" value={app.web_port ?? 'none'} />
      </Card>
      <View style={s.wrap}>
        <LinkChip label="Docs" url={app.links.docs} />
        <LinkChip label="GitHub" url={app.links.github} />
        <LinkChip label="Website" url={app.links.website} />
        <LinkChip label="Support" url={app.links.support} />
      </View>
      {reason && <Notice tone="warn" text={reason} />}
      {msg && <Notice tone={msg.tone} text={msg.text} />}
      <View style={s.wrap}>
        <Button
          testID="request"
          label={busy ? 'Sending…' : app.installed ? 'Ask to remove' : 'Ask to install'}
          variant={app.installed ? 'danger' : 'primary'}
          disabled={busy || !!reason}
          onPress={() => void ask()}
        />
      </View>
      {msg?.tone === 'ok' && (
        <Button variant="secondary" label="Open Approvals" onPress={() => nav.navigate('Tabs', { screen: 'Approvals' })} />
      )}
      <Text style={{ color: t.muted, fontSize: 12 }}>
        Installing creates an action on the hub. The hub re-checks the scan when an owner approves.
      </Text>
    </Screen>
  );
}
