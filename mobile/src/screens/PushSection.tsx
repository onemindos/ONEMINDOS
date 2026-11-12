// SPDX-License-Identifier: Apache-2.0
// Settings → Push: turn content-free push on or off for this phone (mobile/docs/push.md).
import { useCallback, useEffect, useState } from 'react';
import { Platform, View } from 'react-native';
import { blockerMessage, disablePush, enablePush, loadPushRecord, platformTransport, PushError, pushBlocker, type PushBlocker, type PushRecord } from '../lib/push';
import { useSignedIn } from '../session';
import { Button, Card, H2, Notice, P, Row, s } from '../ui/bits';

export function PushSection({ deviceApproved, deviceName }: { deviceApproved: boolean; deviceName: string }) {
  const { api, features, connection } = useSignedIn();
  const hubUrl = connection.mode === 'live' ? connection.hubUrl : undefined;
  const [rec, setRec] = useState<PushRecord>();
  const [blocker, setBlocker] = useState<PushBlocker>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>();
  const transport = platformTransport();

  const refresh = useCallback(async () => {
    if (!hubUrl) return;
    setRec(await loadPushRecord(hubUrl));
    setBlocker(await pushBlocker(transport, { features, deviceApproved }).catch(() => undefined));
    // transport is stable per platform; features and approval drive the answer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hubUrl, features, deviceApproved]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!hubUrl)
    return (
      <>
        <H2>Push</H2>
        <Card>
          <P muted small>Push is not part of the demo: it needs your own box.</P>
        </Card>
      </>
    );

  async function turnOn() {
    setBusy(true);
    setMsg(undefined);
    try {
      setRec(await enablePush(api, transport, { features, hubUrl: hubUrl!, label: deviceName, deviceApproved }));
      setMsg({ text: 'Push is on. The box will ping this phone with ids only; the text comes from the box.', ok: true });
    } catch (e) {
      setMsg({ text: e instanceof PushError ? blockerMessage(e.blocker) : `Push could not be turned on: ${String(e)}`, ok: false });
    } finally {
      setBusy(false);
      void refresh();
    }
  }

  async function turnOff() {
    setBusy(true);
    await disablePush(api, transport, rec);
    setRec(undefined);
    setMsg({ text: 'Push is off for this phone.', ok: true });
    setBusy(false);
    void refresh();
  }

  const how =
    Platform.OS === 'android'
      ? 'Through UnifiedPush and the ntfy app, connected to your box. Google is not involved.'
      : 'Through Apple\'s push service and the OneMind relay. Apple sees only that a ping arrived, never what it was about. Until the iPhone extension ships (F-4), the alert says "Something new on your box" and the app shows the text when opened.';
  return (
    <>
      <H2>Push</H2>
      <Card testID="push">
        <Row label="Push" value={rec ? `on since ${rec.since.slice(0, 10)}` : 'off'} />
        <P muted small>{how}</P>
        {!rec && blocker && <Notice tone={blocker === 'hub_unsupported' ? 'info' : 'warn'} text={blockerMessage(blocker)} />}
        {msg && <Notice tone={msg.ok ? 'ok' : 'bad'} text={msg.text} />}
        <View style={s.wrap}>
          {rec ? (
            <Button testID="push-off" variant="secondary" label="Turn off push" disabled={busy} onPress={() => void turnOff()} />
          ) : (
            <Button
              testID="push-on"
              label={busy ? 'Turning on…' : 'Turn on push'}
              disabled={busy || blocker === 'hub_unsupported' || blocker === 'needs_device' || blocker === 'no_module'}
              onPress={() => void turnOn()}
            />
          )}
        </View>
      </Card>
    </>
  );
}
