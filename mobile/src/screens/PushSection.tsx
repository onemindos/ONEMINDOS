// SPDX-License-Identifier: Apache-2.0
// Settings → Push: turn content-free push on or off for this phone (mobile/docs/push.md). On Android a
// three-step guide (§3.1 there): (1) ntfy on the box, asked for through Approvals; (2) the ntfy app on
// this phone, pointed at the box's ntfy; (3) turn on, then the box's registration and the last ping.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppState, Linking, Platform, Share, View } from 'react-native';
import type { PushRegistration } from '../api/types';
import { requestAction } from '../lib/approvals';
import { loadThisPhone, type ThisPhone } from '../lib/install';
import {
  blockerMessage,
  boxNtfy,
  boxNtfyAddress,
  disablePush,
  enablePush,
  loadPushRecord,
  NTFY_APP,
  NTFY_FDROID,
  platformTransport,
  PushError,
  pushBlocker,
  urlHost,
  type BoxNtfy,
  type PushBlocker,
  type PushRecord,
  type PushTransport,
} from '../lib/push';
import { lastPing } from '../pushPings';
import { useSignedIn } from '../session';
import { Button, Card, H2, Notice, P, Row, s } from '../ui/bits';

type Msg = { text: string; ok: boolean };

export function PushSection({
  deviceApproved,
  phone,
  os = Platform.OS,
  transport: given,
}: {
  deviceApproved: boolean;
  phone: ThisPhone | undefined;
  /** For tests: the platform and the push transport; defaults to this phone's. */
  os?: string;
  transport?: PushTransport;
}) {
  const { api, features, connection, canRequest } = useSignedIn();
  const hubUrl = connection.mode === 'live' ? connection.hubUrl : undefined;
  const android = os === 'android';
  const transport = useMemo(() => given ?? platformTransport(os), [given, os]);
  const [rec, setRec] = useState<PushRecord>();
  const [blocker, setBlocker] = useState<PushBlocker>();
  const [ntfy, setNtfy] = useState<BoxNtfy | 'unknown'>();
  const [reg, setReg] = useState<PushRegistration | null>();
  const [pinged, setPinged] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>();

  const refresh = useCallback(async () => {
    if (!hubUrl) return;
    const r = await loadPushRecord(hubUrl);
    setRec(r);
    setBlocker(await pushBlocker(transport, { features, deviceApproved }).catch(() => undefined));
    if (android) {
      const [apps, actions] = await Promise.all([api.apps().catch(() => undefined), api.actions().catch(() => [])]);
      setNtfy(apps ? boxNtfy(apps, actions) : 'unknown');
    }
    if (r) {
      const regs = await api.pushRegistrations().catch(() => undefined);
      setReg(regs ? (regs.find((x) => x.id === r.id) ?? null) : undefined);
      setPinged(await lastPing().catch(() => undefined));
    }
  }, [hubUrl, transport, features, deviceApproved, android, api]);

  useEffect(() => {
    void refresh();
    // Back from installing ntfy, setting its server or deciding in Approvals: look again.
    const sub = AppState.addEventListener('change', (st) => st === 'active' && void refresh());
    return () => sub.remove();
  }, [refresh]);

  if (!hubUrl) return null;

  async function askNtfy() {
    setBusy(true);
    setMsg(undefined);
    try {
      await requestAction(api, 'app.install', NTFY_APP);
      setNtfy('requested');
      setMsg({ text: 'Request sent. ntfy is installed on the box only after an owner approves it in Approvals.', ok: true });
    } catch (e) {
      setMsg({ text: `Could not send the request: ${String(e instanceof Error ? e.message : e)}`, ok: false });
    } finally {
      setBusy(false);
    }
  }

  async function turnOn() {
    setBusy(true);
    setMsg(undefined);
    try {
      const me = phone ?? (await loadThisPhone());
      setRec(await enablePush(api, transport, { features, hubUrl: hubUrl!, label: me.name, installId: me.installId, deviceApproved }));
      setMsg({ text: 'Push is on. The box will ping this phone with ids only; the text comes from the box.', ok: true });
    } catch (e) {
      setMsg({ text: e instanceof PushError ? blockerMessage(e.blocker, os) : `Push could not be turned on: ${String(e)}`, ok: false });
    } finally {
      setBusy(false);
      void refresh();
    }
  }

  async function turnOff() {
    setBusy(true);
    await disablePush(api, transport, rec);
    setRec(undefined);
    setReg(undefined);
    setMsg({ text: 'Push is off for this phone.', ok: true });
    setBusy(false);
    void refresh();
  }

  const how = android
    ? 'Through UnifiedPush and the ntfy app, connected to your box. Google is not involved.'
    : 'Through Apple\'s push service and the OneMind relay. Apple sees only that a ping arrived, never what it was about. Until the iPhone extension ships (F-4), the alert says "Something new on your box" and the app shows the text when opened.';
  const hardBlock = blocker === 'hub_unsupported' || blocker === 'needs_device' || blocker === 'no_module';
  const address = boxNtfyAddress(hubUrl);
  const noDistributor = blocker === 'no_distributor';
  const boxNotReady = ntfy === 'missing' || ntfy === 'requested';
  const offBox = android && rec?.platform === 'unifiedpush' && address && urlHost(rec.handle) !== urlHost(address) ? urlHost(rec.handle) : undefined;

  const turnOnButton = (
    <Button
      testID="push-on"
      label={busy ? 'Turning on…' : 'Turn on push'}
      disabled={busy || hardBlock || (android && (noDistributor || boxNotReady))}
      onPress={() => void turnOn()}
    />
  );

  return (
    <>
      <H2>Push</H2>
      <Card testID="push">
        <Row label="Push" value={rec ? `on since ${rec.since.slice(0, 10)}` : 'off'} />
        <P muted small>{how}</P>
        {!rec && blocker && (hardBlock || !android) && <Notice tone={blocker === 'hub_unsupported' ? 'info' : 'warn'} text={blockerMessage(blocker, os)} />}
        {msg && <Notice tone={msg.ok ? 'ok' : 'bad'} text={msg.text} />}
        {rec ? (
          <View testID="push-registration">
            {reg ? (
              <>
                <Row label="Registered as" value={reg.label || 'this phone'} />
                <Row label="Registered since" value={(reg.created_at ?? rec.since).slice(0, 10)} />
              </>
            ) : reg === null ? (
              <Notice tone="warn" text="The box has no registration for this phone any more. Turn push off and on again." />
            ) : null}
            {offBox && (
              <Notice
                tone="warn"
                text={`Pings for this phone go through ${offBox}, not your box's ntfy. In the ntfy app set the default server to ${address}, then turn push off and on again.`}
              />
            )}
            <Row label="Last ping" value={pinged ? pinged.replace('T', ' ').slice(0, 16) : 'none yet'} />
            <P muted small>The box has no test-ping route yet; this shows when the last ping reached this phone, also while the app was closed.</P>
          </View>
        ) : null}
        {!rec && android && !hardBlock ? (
          <>
            <View testID="push-step-box">
              <P>1. ntfy on your box</P>
              {ntfy === 'installed' ? (
                <P muted small>ntfy is installed on the box. Pings for this phone go through it.</P>
              ) : ntfy === 'requested' ? (
                <P muted small>A request to install ntfy waits in Approvals. Push can be turned on once an owner approves it and it is running.</P>
              ) : ntfy === 'missing' ? (
                <>
                  <P muted small>Push travels through the box&apos;s own ntfy server, which is not installed yet. Installing it is an approval, like any change.</P>
                  {canRequest === 'no' ? (
                    <P muted small>Ask an owner to install ntfy from the Market.</P>
                  ) : (
                    <View style={s.wrap}>
                      <Button testID="push-ask-ntfy" label={busy ? 'Sending…' : 'Ask to install ntfy on the box'} disabled={busy} onPress={() => void askNtfy()} />
                    </View>
                  )}
                </>
              ) : ntfy === 'absent' ? (
                <P muted small>This box&apos;s Market has no ntfy app. If you run ntfy elsewhere, point the phone&apos;s ntfy app at it.</P>
              ) : ntfy === 'unknown' ? (
                <P muted small>Could not read the box&apos;s apps. If ntfy is installed on the box, carry on.</P>
              ) : null}
            </View>
            <View testID="push-step-phone">
              <P>2. ntfy on this phone</P>
              {address ? (
                <>
                  <Row label="Box ntfy address" value={address} />
                  <View style={s.wrap}>
                    <Button testID="push-copy" variant="secondary" label="Copy or share address" onPress={() => void Share.share({ message: address })} />
                  </View>
                </>
              ) : (
                <P muted small>
                  The box&apos;s ntfy address is ntfy.&lt;box name&gt;.local (for example ntfy.onemind.local). Connect to the box by its .local name to see it here.
                </P>
              )}
              {noDistributor ? (
                <>
                  <P muted small>Install the ntfy app from F-Droid, open its Settings, set Default server to the box&apos;s ntfy address, then come back here.</P>
                  <View style={s.wrap}>
                    <Button testID="push-get-ntfy" variant="secondary" label="Get ntfy (F-Droid)" onPress={() => void Linking.openURL(NTFY_FDROID).catch(() => undefined)} />
                  </View>
                </>
              ) : blocker === undefined || blocker === 'no_permission' ? (
                <P muted small>ntfy is on this phone. Its Default server must be the box&apos;s ntfy address.</P>
              ) : null}
            </View>
            <View testID="push-step-on">
              <P>3. Turn on push</P>
              {blocker === 'no_permission' && <Notice tone="warn" text={blockerMessage(blocker, os)} />}
              <View style={s.wrap}>{turnOnButton}</View>
            </View>
          </>
        ) : (
          <View style={s.wrap}>
            {rec ? <Button testID="push-off" variant="secondary" label="Turn off push" disabled={busy} onPress={() => void turnOff()} /> : turnOnButton}
          </View>
        )}
      </Card>
    </>
  );
}
