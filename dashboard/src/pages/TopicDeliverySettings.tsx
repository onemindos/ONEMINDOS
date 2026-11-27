// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState, type FormEvent } from 'react';
import { OneMind } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { useNow, usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

export function TopicDeliverySettings({ channels }: { channels: readonly { id: string; label: string }[] }) {
  const { token } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const preferences = usePoll(() => sdk.notifications.preferences.get(), 0);
  const devices = usePoll(() => sdk.notifications.devices(), 0);
  const [topic, setTopic] = useState('');
  const [channel, setChannel] = useState('in_app');
  const [days, setDays] = useState<number>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const now = useNow(1000);
  const current = preferences.data;
  const savedDays = typeof current?.prefs.retention_days === 'number' ? current.prefs.retention_days : 90;
  const mutes: Array<{ topic: string; channel: string }> = Array.isArray(current?.prefs.mutes) ? current.prefs.mutes : [];
  const targets = [{ id: 'in_app', label: 'In-app' }, { id: '*', label: 'All destinations' }, ...channels, ...(devices.data ?? [])];
  const quiet = current?.prefs.quiet_hours as { tz: string; from: string; to: string; except_severity?: string[]; except_topics?: string[] } | null;
  const digest = current?.prefs.digest as { enabled: boolean; at: string } | undefined;
  const silence = current?.prefs.silence as { until: string; reason: string } | null;
  const active = silence && Date.parse(silence.until) > now;

  async function save(changes: Record<string, unknown>) {
    if (!current || saving) return;
    setSaving(true);
    setError('');
    try {
      await sdk.notifications.preferences.save({ ...current.prefs, ...changes }, current.etag);
      await preferences.reload();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not save notification preferences.');
      await preferences.reload();
    } finally {
      setSaving(false);
    }
  }

  function addMute(event: FormEvent) {
    event.preventDefault();
    const name = topic.trim();
    if (name && !mutes.some((mute) => mute.topic === name && mute.channel === channel))
      void save({ mutes: [...mutes, { topic: name, channel }] });
  }

  return (
    <Card title="Topic delivery and retention">
      <p>Muted topics stay in your inbox until their retention period ends.</p>
      {preferences.error && <p role="alert">{preferences.error.message}</p>}
      {error && <p role="alert">{error}</p>}
      {devices.error && <p role="status">Could not load notification devices.</p>}
      {!!devices.data?.length && <ul aria-label="Notification devices">{devices.data.map((device) => (
        <li key={device.id}>{device.label} · {device.platform} · {device.state}</li>
      ))}</ul>}
      {current && <>
        {active ? <section aria-label="Active silence" className="om-note">
          <p>Silenced until {new Date(silence.until).toLocaleTimeString()} · {silence.reason}</p>
          <Button disabled={saving} onClick={() => void save({ silence: null })}>End silence</Button>
        </section> : <form className="dash-actions" onSubmit={(event) => {
          event.preventDefault();
          const reason = String(new FormData(event.currentTarget).get('reason') ?? '').trim();
          if (reason) void save({ silence: { until: new Date(sdk.hubNow() + 7_200_000).toISOString(), reason } });
        }}>
          <label>Silence reason <input name="reason" required maxLength={200} /></label>
          <Button type="submit" disabled={saving}>Snooze for 2 hours</Button>
        </form>}
        <form className="dash-actions" key={`quiet-${current.etag}`} onSubmit={(event) => {
          event.preventDefault();
          const input = new FormData(event.currentTarget);
          void save({ quiet_hours: { ...quiet, tz: input.get('tz'), from: input.get('from'), to: input.get('to') } });
        }}>
          <label>Quiet hours start <input name="from" type="time" defaultValue={quiet?.from ?? '22:00'} required /></label>
          <label>Quiet hours end <input name="to" type="time" defaultValue={quiet?.to ?? '07:00'} required /></label>
          <label>Time zone <input name="tz" defaultValue={quiet?.tz ?? Intl.DateTimeFormat().resolvedOptions().timeZone} required /></label>
          <Button type="submit" disabled={saving}>Save quiet hours</Button>
          {quiet && <Button disabled={saving} onClick={() => void save({ quiet_hours: null })}>Turn off quiet hours</Button>}
        </form>
        <form className="dash-actions" key={`digest-${current.etag}`} onSubmit={(event) => {
          event.preventDefault();
          const input = new FormData(event.currentTarget);
          void save({ digest: { enabled: input.has('enabled'), at: input.get('at') } });
        }}>
          <label><input type="checkbox" name="enabled" defaultChecked={digest?.enabled} /> Daily digest</label>
          <label>Digest time <input name="at" type="time" defaultValue={digest?.at ?? '08:00'} required /></label>
          <Button type="submit" disabled={saving}>Save digest</Button>
        </form>
      </>}
      <form className="dash-actions" onSubmit={addMute}>
        <label>Topic <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="approvals.*" required /></label>
        <label>Destination <select value={channel} onChange={(event) => setChannel(event.target.value)}>
          {targets.map((target) => <option key={target.id} value={target.id}>{target.label}</option>)}
        </select></label>
        <Button type="submit" disabled={!current || saving}>Mute topic</Button>
      </form>
      {mutes.length > 0 && <ul>{mutes.map((mute, index) => (
        <li key={JSON.stringify(mute)}>{mute.topic} · {targets.find((target) => target.id === mute.channel)?.label ?? mute.channel}{' '}
          <Button size="sm" disabled={saving} onClick={() => void save({ mutes: mutes.filter((_, position) => index !== position) })}>Unmute</Button>
        </li>
      ))}</ul>}
      <form className="dash-actions" onSubmit={(event) => {
        event.preventDefault();
        if (days !== undefined && Number.isInteger(days) && days >= 1 && days <= 90) void save({ retention_days: days });
      }}>
        <label>Keep inbox items (days) <input type="number" min={1} max={90} value={days ?? savedDays} required
          onChange={(event) => setDays(event.target.value ? event.target.valueAsNumber : undefined)} /></label>
        <Button type="submit" disabled={!current || saving || days === undefined || days === savedDays}>Save retention</Button>
      </form>
    </Card>
  );
}
