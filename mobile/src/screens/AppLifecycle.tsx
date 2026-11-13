// SPDX-License-Identifier: Apache-2.0
// Start, stop, restart, update and remove for an installed app (contract §12.40). Each one is a REQUEST:
// the phone shows the plan the hub would run (files nothing), sends the request bound to that plan's hash,
// and the request waits in Approvals for an owner. Nothing here changes the box by itself.
import { useNavigation } from '@react-navigation/native';
import { useState } from 'react';
import { Text, View } from 'react-native';
import { OP } from '../api/client';
import type { Action, CatalogApp, LifecycleType } from '../api/types';
import { useHubData } from '../data';
import { LIFECYCLE_LABEL, lifecycleOptions, previewLifecycle, requestError, requestLifecycle, type LifecyclePreview } from '../lib/manage';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H2, Notice, P, s } from '../ui/bits';
import { font, useTheme } from '../ui/theme';

export function AppLifecycle({ app }: { app: CatalogApp }) {
  const t = useTheme();
  const nav = useNavigation();
  const { api, features, canRequest } = useSignedIn();
  const { actions, reload } = useHubData();
  const [pick, setPick] = useState<{ type: LifecycleType; p: LifecyclePreview }>();
  const [filed, setFiled] = useState<Action>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' | 'warn' }>();

  if (!features.has(OP.appPlan) || !app.installed) return null;
  const options = lifecycleOptions(app);
  const waiting = (actions ?? []).find((a) => a.state === 'awaiting_approval' && a.params.app_id === app.id);
  const blocked =
    canRequest === 'no' ? 'Only an owner (or an agent) can ask for changes.' : waiting ? `A request (${waiting.type}) is already waiting for approval.` : undefined;

  async function preview(type: LifecycleType) {
    setBusy(true);
    setMsg(undefined);
    setFiled(undefined);
    try {
      const p = await previewLifecycle(api, app.id, type);
      if (p.refused) setMsg({ text: `The hub will not file this now: ${p.preview.reason ?? 'the app is in a state it cannot start from'}.`, tone: 'warn' });
      else setPick({ type, p });
    } catch (e) {
      setMsg({ text: requestError(e, `the ${LIFECYCLE_LABEL[type].toLowerCase()} plan`).text, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!pick) return;
    setBusy(true);
    try {
      const a = await requestLifecycle(api, app.id, pick.type, pick.p.preview.plan_sha256);
      setFiled(a);
      setPick(undefined);
      setMsg({ text: 'Request sent. Nothing has changed yet: it waits in Approvals until an owner decides.', tone: 'ok' });
      await reload();
    } catch (e) {
      setMsg({ text: requestError(e, `the ${LIFECYCLE_LABEL[pick.type].toLowerCase()}`).text, tone: 'bad' });
      setPick(undefined);
    } finally {
      setBusy(false);
    }
  }

  const plan = pick?.p.preview.plan;
  const vols = plan?.volumes?.length ?? 0;
  return (
    <>
      <H2>Manage</H2>
      {options.length === 0 ? (
        <P muted small>This app is {app.status.replace(/_/g, ' ')}; actions are available when it settles.</P>
      ) : (
        <View style={s.wrap}>
          {options.map((o) => (
            <Button
              key={o}
              testID={`lifecycle-${o}`}
              label={LIFECYCLE_LABEL[o]}
              variant={o === 'app.remove' ? 'danger' : 'secondary'}
              disabled={busy || !!blocked || !!pick}
              onPress={() => void preview(o)}
            />
          ))}
        </View>
      )}
      {blocked && <Notice tone="warn" text={blocked} />}
      {pick && plan && (
        <Card testID="lifecycle-plan">
          <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold }}>
            {LIFECYCLE_LABEL[pick.type]} {app.name}
          </Text>
          <View style={s.wrap}>
            {pick.p.preview.risk ? <Badge label={pick.p.preview.risk} tone={pick.p.preview.risk === 'destructive' ? 'bad' : 'info'} /> : null}
            {plan.from_version && plan.to_version ? <Badge label={`${plan.from_version} → ${plan.to_version}`} /> : null}
            {vols > 0 ? <Badge label={`${vols} volume${vols === 1 ? '' : 's'}`} /> : null}
          </View>
          <P>{plan.summary ?? 'The hub sent a plan without a summary.'}</P>
          {(plan.warnings ?? []).map((w, i) => (
            <Notice key={i} tone="warn" text={w} />
          ))}
          <P muted small>Sending this only asks. An owner sees this same plan in Approvals and decides.</P>
          <View style={s.wrap}>
            <Button testID="lifecycle-cancel" variant="secondary" label="Cancel" onPress={() => setPick(undefined)} />
            <Button testID="lifecycle-send" label={busy ? 'Sending…' : 'Send request'} disabled={busy} onPress={() => void send()} />
          </View>
        </Card>
      )}
      {msg && <Notice tone={msg.tone} text={msg.text} />}
      {filed && (
        <View style={s.wrap}>
          <Badge label={filed.state.replace(/_/g, ' ')} tone="info" />
          <Button variant="secondary" label="Open Approvals" onPress={() => nav.navigate('Tabs', { screen: 'Approvals' })} />
        </View>
      )}
    </>
  );
}
