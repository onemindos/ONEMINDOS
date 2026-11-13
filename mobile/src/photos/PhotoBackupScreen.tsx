// SPDX-License-Identifier: Apache-2.0
// Photo backup: an honest status, live progress, the rules (Wi-Fi, charging, albums), what the box
// says about this phone's items, and what happens while the app is closed.
import { useNavigation } from '@react-navigation/native';
import { Pressable, Switch, Text, View } from 'react-native';
import { useNow } from '../data';
import { formatAgo } from '../lib/time';
import { Badge, Button, Card, H2, Notice, P, Row, Screen, s } from '../ui/bits';
import { space, useTheme } from '../ui/theme';
import { usePhotoBackup } from './context';
import { mb, summarize } from './status';

function ProgressBar({ value, label }: { value: number; label: string }) {
  const t = useTheme();
  const pct = Math.max(0, Math.min(1, value));
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      accessibilityValue={{ min: 0, max: 100, now: Math.round(pct * 100) }}
      style={{ height: 8, borderRadius: 4, backgroundColor: t.neutralBg, overflow: 'hidden' }}
    >
      <View style={{ width: `${pct * 100}%`, height: 8, backgroundColor: t.accent }} />
    </View>
  );
}

function Toggle({ label, hint, value, onChange, disabled, testID }: { label: string; hint: string; value: boolean; onChange: (v: boolean) => void; disabled?: boolean; testID?: string }) {
  const t = useTheme();
  return (
    <View style={[s.row, { alignItems: 'center' }]}>
      <View style={{ flexShrink: 1, gap: 2 }}>
        <Text style={{ color: t.text, fontSize: 15, fontWeight: '600' }}>{label}</Text>
        <Text style={{ color: t.muted, fontSize: 13 }}>{hint}</Text>
      </View>
      <Switch testID={testID} accessibilityLabel={label} value={value} onValueChange={onChange} disabled={disabled} />
    </View>
  );
}

const NET: Record<string, string> = { wifi: 'Wi-Fi', cellular: 'mobile data', other: 'a network OneMind cannot identify', none: 'no network' };
const POWER: Record<string, string> = { charging: 'charging', battery: 'on battery', unknown: 'charging state unknown' };

export function PhotoBackupScreen() {
  const t = useTheme();
  const nav = useNavigation();
  const now = useNow(5000);
  const b = usePhotoBackup();
  const v = summarize({ ...b, now });
  const { settings, ledger, progress } = b;
  const ok = b.availability.state === 'ok';
  const failed = Object.values(ledger?.items ?? {}).filter((i) => i.inSelection && i.state === 'failed');
  const cov = ledger?.coverage;

  return (
    <Screen testID="photo-backup">
      {b.demo ? <Notice text="Demo: a made-up photo library and an in-memory OneMind. Nothing leaves this phone." /> : null}

      <Card testID="photo-status">
        <View style={s.row}>
          <Text accessibilityRole="header" style={{ color: t.text, fontSize: 19, fontWeight: '700', flexShrink: 1 }}>
            {v.headline}
          </Text>
        </View>
        {v.counts.total > 0 && !b.running ? (
          <View style={s.wrap}>
            <Badge label={`${v.counts.done} on OneMind`} tone={v.counts.done ? 'ok' : 'neutral'} />
            <Badge label={`${v.counts.waiting} waiting`} tone={v.counts.waiting ? 'info' : 'neutral'} />
            {v.counts.failed ? <Badge label={`${v.counts.failed} failed`} tone="bad" /> : null}
          </View>
        ) : null}
        {v.lines.map((l) => (
          <P key={l} muted small>
            {l}
          </P>
        ))}
        {b.running && progress ? (
          <View style={{ gap: space.xs, marginTop: space.xs }} testID="photo-progress">
            <ProgressBar value={progress.total ? progress.done / progress.total : 0} label="Items on your OneMind" />
            {progress.current && progress.current.size > 0 ? (
              <>
                <P small>
                  {progress.current.fileName} · {mb(progress.current.sent)} of {mb(progress.current.size)}
                </P>
                <ProgressBar value={progress.current.sent / progress.current.size} label={`Uploading ${progress.current.fileName}`} />
              </>
            ) : null}
            <P muted small>{mb(progress.bytesThisRun)} sent this time</P>
          </View>
        ) : null}
        <View style={[s.wrap, { marginTop: space.xs }]}>
          {b.running ? (
            <Button label="Stop" variant="secondary" onPress={b.stop} testID="photo-stop" />
          ) : settings.enabled ? (
            <Button label="Back up now" onPress={() => void b.runNow()} disabled={!!v.cannotRun} testID="photo-run" />
          ) : (
            <Button label="Turn on photo backup" onPress={() => void b.updateSettings({ enabled: true })} disabled={!ok} testID="photo-enable" />
          )}
        </View>
        {settings.enabled && v.cannotRun && !b.running ? <P muted small>{v.cannotRun}.</P> : null}
        {b.permission === 'denied' || b.permission === 'undetermined' ? (
          <Button label="Allow photo access" variant="secondary" onPress={() => void b.requestPermission()} />
        ) : null}
      </Card>

      <H2>Rules</H2>
      <Card>
        <Toggle label="Back up photos and videos" hint="Sends new items to your OneMind." value={settings.enabled} onChange={(x) => void b.updateSettings({ enabled: x })} disabled={!ok} testID="photo-toggle-enabled" />
        <Toggle label="Only on Wi-Fi" hint={settings.wifiOnly ? 'Never uses mobile data.' : 'May use mobile data, which can cost money.'} value={settings.wifiOnly} onChange={(x) => void b.updateSettings({ wifiOnly: x })} testID="photo-toggle-wifi" />
        <Toggle label="Only while charging" hint="Saves battery; backup waits until the phone is plugged in." value={settings.chargingOnly} onChange={(x) => void b.updateSettings({ chargingOnly: x })} testID="photo-toggle-charging" />
        <Pressable accessibilityRole="button" onPress={() => nav.navigate('PhotoAlbums')} testID="photo-albums-link">
          <Row label="Albums" value={settings.albums === 'all' ? 'All photos ›' : `${settings.albums.length} album${settings.albums.length === 1 ? '' : 's'} ›`} />
        </Pressable>
        {b.conditions ? (
          <P muted small>
            Right now: {NET[b.conditions.network]}, {POWER[b.conditions.power]}.
          </P>
        ) : null}
      </Card>

      <H2>On your OneMind</H2>
      <Card testID="photo-coverage">
        {cov ? (
          <>
            <Row label="Received from this phone" value={String(cov.on_box)} />
            <Row label="In a OneMind backup" value={String(cov.backed_up)} />
            <Row label="Backup restore-checked" value={String(cov.verified)} />
            <P muted small>
              Received means one copy on your OneMind. An item is only safe to delete from this phone once a backup of your OneMind holds it and that backup has passed a restore check. As of{' '}
              {formatAgo(Math.max(0, Math.floor((now - cov.fetchedAt) / 1000)))}.
            </P>
          </>
        ) : (
          <P muted small>Your OneMind has not reported on this phone’s items yet.</P>
        )}
        <P muted small>Free up space on this phone is not offered yet. It will list only restore-checked items.</P>
      </Card>

      <H2>When the app is closed</H2>
      <Card>
        <P small>
          {b.demo
            ? 'The demo only backs up while it is open.'
            : b.background === 'restricted'
              ? 'Background backup is off for OneMind in this phone’s settings (Background App Refresh or battery saver). Backup only runs while the app is open.'
              : 'The phone decides when OneMind may work in the background: at most every 15 minutes, often only overnight while charging on Wi-Fi. A large video can take several turns; each one continues where the last stopped. Opening the app backs up right away.'}
        </P>
        {b.host ? (
          <P muted small>
            Photos go only to {b.host}, over HTTPS. They are never sent over plain HTTP.
          </P>
        ) : null}
        {ledger?.lastRun ? (
          <P muted small>
            Last run {formatAgo(Math.max(0, Math.floor((now - ledger.lastRun.endedAt) / 1000)))} ({ledger.lastRun.trigger === 'background' ? 'in the background' : 'app open'}): {ledger.lastRun.uploaded} sent, {ledger.lastRun.deduped} already there, {mb(ledger.lastRun.bytes)}.
          </P>
        ) : null}
      </Card>

      {failed.length ? (
        <>
          <H2>Could not send ({failed.length})</H2>
          <Card testID="photo-failed">
            {failed.slice(0, 20).map((i) => (
              <Row key={i.key} label={i.fileName} value={i.error ?? 'failed'} />
            ))}
            <P muted small>OneMind tries each item up to three times.</P>
          </Card>
        </>
      ) : null}
    </Screen>
  );
}
