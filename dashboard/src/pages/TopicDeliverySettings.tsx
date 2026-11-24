// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState, type FormEvent } from 'react';
import { OneMind } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

export function TopicDeliverySettings({ channels }: { channels: readonly { id: string; label: string }[] }) {
  const { token } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const preferences = usePoll(() => sdk.notifications.preferences.get(), 0);
  const [topic, setTopic] = useState('');
  const [channel, setChannel] = useState('in_app');
  const [days, setDays] = useState<number>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const current = preferences.data;
  const savedDays = typeof current?.prefs.retention_days === 'number' ? current.prefs.retention_days : 90;
  const mutes: Array<{ topic: string; channel: string }> = Array.isArray(current?.prefs.mutes) ? current.prefs.mutes : [];
  const targets = [{ id: 'in_app', label: 'In-app' }, { id: '*', label: 'All destinations' }, ...channels];

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
