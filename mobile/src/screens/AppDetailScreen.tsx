// SPDX-License-Identifier: Apache-2.0
import { NavigationContext, useNavigation, useRoute, type RouteProp } from '@react-navigation/native';
import { useContext, useLayoutEffect, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { OP } from '../api/client';
import { ApiError, type Action, type ActionType } from '../api/types';
import { useHubData, useNow } from '../data';
import { principalLabel, requestAction, sortByRecent } from '../lib/approvals';
import { asksParent } from '../lib/people';
import { appOpenUrl } from '../lib/health';
import { installBlockReason } from '../lib/scan';
import type { RootParams } from '../nav';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H1, LinkChip, Notice, P, Screen, StateBadge, s } from '../ui/bits';
import { font, touchTarget, useTheme } from '../ui/theme';
import { AppLifecycle } from './AppLifecycle';
import { TIER_TONE } from './AppsScreen';
import { AppFacts, AppTrust, useAppPageDetails } from './AppPageFacts';
import { AppInstallWaiting } from './AppInstallWaiting';

export function AppDetailScreen() {
  const t = useTheme();
  const nav = useNavigation();
  const screenNav = useContext(NavigationContext);
  useLayoutEffect(() => screenNav?.setOptions({ headerShown: false }), [screenNav]);
  const { params } = useRoute<RouteProp<RootParams, 'AppDetail'>>();
  const { api, canRequest, connection, features, principal } = useSignedIn();
  // Teen and Child never decide anything: their request goes to a parent's Approvals (FAM-01).
  const young = asksParent(principal?.role);
  const { apps, actions, hubOffsetMs, reload } = useHubData();
  const now = useNow() + (hubOffsetMs ?? 0);
  const extra = useAppPageDetails(params.id);
  const [reply, setReply] = useState<{ action: Action; label: string }>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' }>();
  const app = apps?.find((a) => a.id === params.id);
  if (!app)
    return (
      <Screen>
        <P muted>This app is not in the hub's catalog.</P>
      </Screen>
    );

  const appReply = reply?.action.params.app_id === app.id ? reply : undefined;
  const waiting = sortByRecent(actions ?? []).find((a) =>
    a.state === 'awaiting_approval' && a.params.app_id === app.id && a.id !== appReply?.action.id);
  const installWaiting = waiting?.type === 'app.install' || waiting?.type === 'app.update' ? waiting : undefined;
  const outcome = appReply && ((actions ?? []).find((a) => a.id === appReply.action.id && a.state !== 'awaiting_approval') ?? appReply.action);
  const scanBlock = installBlockReason(app, now);
  const licenceClass = extra?.details?.licence_class ?? ('licence_class' in app ? app.licence_class : undefined);
  const licenceBlock = licenceClass === 'blocked' || licenceClass === 'unknown'
    ? 'The hub needs licence acceptance before it can approve this request.' : undefined;
  const type: ActionType = app.installed ? 'app.remove' : 'app.install';
  const blockReason = type === 'app.install' ? scanBlock : undefined;
  const reason =
    young
      ? 'Teen and Child sign-ins cannot file requests yet (no hub route for it). Ask a parent to add the app for you.'
      : canRequest === 'no' && !young
        ? 'Only an owner (or an agent) can ask for changes.'
        : waiting
          ? `A request is already waiting for approval (from ${principalLabel(waiting.requested_by)}).`
          : blockReason;
  const quality = extra?.details?.scan?.quality;
  const openUrl = appOpenUrl(app, connection.mode === 'live' ? connection.hubUrl : undefined);
  // With §12.40 plans the installed app's actions (including remove) go through AppLifecycle.
  const managed = app.installed && features.has(OP.appPlan);

  async function ask() {
    setBusy(true);
    setMsg(undefined);
    setReply(undefined);
    try {
      await requestAction(api, type, app!.id);
      setMsg({ text: young ? 'Asked. Your request is with a parent. Nothing is installed until they say yes.' : 'Request sent. It waits in Approvals until an owner decides.', tone: 'ok' });
      await reload();
    } catch (e) {
      setMsg({ text: young && e instanceof ApiError && (e.code === 'permission_denied' || e.code === 'not_found') ? 'The hub did not accept this request. Ask a parent to add the app for you.' : `Could not send the request: ${e instanceof ApiError ? e.message : String(e)}`, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1 }}>
      <Screen testID="app-detail">
        <Pressable accessibilityRole="button" accessibilityLabel="Back to Market" onPress={() => nav.navigate('Tabs', { screen: 'Apps' })}
          style={{ alignSelf: 'flex-start', justifyContent: 'center', minHeight: touchTarget, minWidth: touchTarget }}>
          <Text style={{ color: t.action, fontSize: font.sm, fontWeight: font.semibold }}>‹ Market</Text>
        </Pressable>
        <View style={[s.wrap, { alignItems: 'flex-start' }]}>
          <View style={{ width: 68, height: 68, borderRadius: 18, backgroundColor: t.raised, borderWidth: 1,
            borderColor: t.border, justifyContent: 'center', alignItems: 'center' }} accessible={false}>
            <Text style={{ color: t.text, fontSize: 26 }}>▦</Text>
          </View>
          <View style={{ flex: 1, gap: 4 }}>
            <H1>{app.name || app.id}</H1>
            {app.description && <P muted small>{app.description}</P>}
            <View style={s.wrap}>
              {quality && quality.tier !== 'none' ? <Badge label={quality.tier} tone="ok" /> :
                app.tier && <Badge label={app.tier} tone={TIER_TONE[app.tier]} />}
              {app.category && <Badge label={app.category} />}
              {app.min_age != null && <Badge label={`age ${app.min_age}+`} />}
              {app.installed && <Badge label={app.status.replace(/_/g, ' ')} tone="info" />}
            </View>
          </View>
        </View>
        <AppFacts app={app} placement={extra?.placement} />
        {outcome && <Card testID="app-decision-result">
          <P>{appReply.label}</P>
          <StateBadge state={outcome.state} />
        </Card>}
        {installWaiting && <AppInstallWaiting key={`${installWaiting.id}:${installWaiting.plan_sha256}`}
          action={installWaiting} now={now} blocked={scanBlock ?? licenceBlock}
          onDecision={(action, label) => setReply({ action, label })} />}
        <AppTrust app={app} details={extra?.details} plan={installWaiting?.plan} />
        <View style={s.wrap}>
          <LinkChip label="Docs" url={app.links.docs} />
          <LinkChip label="GitHub" url={app.links.github} />
          <LinkChip label="Website" url={app.links.website} />
          <LinkChip label="Support" url={app.links.support} />
        </View>
        {openUrl ? <Button testID="open-app" label="Open app" onPress={() => void Linking.openURL(openUrl)} /> : null}
        {reason && !managed && !installWaiting && <Notice tone="warn" text={reason} />}
        {msg && <Notice tone={msg.tone} text={msg.text} />}
        {installWaiting ? null : managed && !young ? (
          <AppLifecycle app={app} />
        ) : (
          <View style={s.wrap}>
            {young ? null : (
              <Button
                testID="request"
                label={busy ? 'Sending…' : app.installed ? 'Ask to remove' : 'Ask to install'}
                variant={app.installed ? 'danger' : 'primary'}
                disabled={busy || !!reason}
                onPress={() => void ask()}
              />
            )}
          </View>
        )}
        {msg?.tone === 'ok' && !young && (
          <Button variant="secondary" label="Open Approvals" onPress={() => nav.navigate('Tabs', { screen: 'Approvals' })} />
        )}
        <Text style={{ color: t.muted, fontSize: 12 }}>
          Installing creates an action on the hub. The hub re-checks the scan when an owner approves.
        </Text>
      </Screen>
    </SafeAreaView>
  );
}
