// SPDX-License-Identifier: Apache-2.0
// First-run software preferences (contract §12.41): box name, time zone and the backup choice. Owner only:
// the hub answers 403 to everyone else, and a person who is known not to be an owner never sees the form.
// Saving these preferences does not start a backup, configure a destination or issue a kit (§12.41), so the
// screen says so and never claims backups are on.
import { useEffect, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { OP } from '../api/client';
import type { BackupDestination, FirstRunSettingsBody } from '../api/types';
import { destinationsFor, requestError, settingsProblem } from '../lib/manage';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Button, Card, H2, Notice, P, s } from '../ui/bits';
import { font, radiusControl, space, useTheme } from '../ui/theme';

const CHOICES: Array<{ id: FirstRunSettingsBody['backup_choice']; label: string }> = [
  { id: 'usb', label: 'USB disk' },
  { id: 'peer', label: 'Another box' },
  { id: 's3', label: 'Cloud (S3)' },
  { id: 'later', label: 'Later' },
];

export function BoxSettingsSection() {
  const t = useTheme();
  const { api, features, canDecide } = useSignedIn();
  const served = features.has(OP.onboardingSettings);
  const known = canDecide !== 'no';
  const settings = useLoad(() => (served && known ? api.onboardingSettings() : Promise.resolve(undefined)), [api, served, known]);
  const dests = useLoad(
    () => (served && known && features.has(OP.backupDestinations) ? api.backupDestinations() : Promise.resolve<BackupDestination[]>([])),
    [api, served, known, features],
  );
  const [form, setForm] = useState<FirstRunSettingsBody>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' }>();
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    const d = settings.data;
    if (d)
      setForm({ box_name: d.box_name ?? '', time_zone: d.time_zone ?? '', backup_choice: d.backup_choice, backup_destination_id: d.backup_destination_id });
  }, [settings.data]);

  if (!served) return null; // an older hub has no first-run settings
  if (!known) return null; // not an owner: nothing to show
  if (settings.forbidden || denied)
    return (
      <>
        <H2>This box</H2>
        <Notice tone="warn" text="Only an owner can see or change the box name, time zone and backup choice." />
      </>
    );
  if (!form) return null;

  const all = dests.data ?? [];
  const options = destinationsFor(form.backup_choice, all);
  const problem = settingsProblem(form, all);
  const input = { borderWidth: 1, borderColor: t.borderStrong, backgroundColor: t.bg, color: t.text, borderRadius: radiusControl, padding: space.md, fontSize: font.md };

  async function save() {
    if (!form || problem) return;
    setBusy(true);
    setMsg(undefined);
    try {
      const saved = await api.saveOnboardingSettings(form);
      setMsg({ text: 'Saved. This sets your preferences only: it does not start a backup or set one up.', tone: 'ok' });
      setForm({ box_name: saved.box_name ?? form.box_name, time_zone: saved.time_zone ?? form.time_zone, backup_choice: saved.backup_choice, backup_destination_id: saved.backup_destination_id });
    } catch (e) {
      const r = requestError(e, 'saving these preferences');
      if (r.forbidden) setDenied(true);
      setMsg({ text: r.text, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <H2>This box</H2>
      <Card testID="box-settings">
        <Text style={{ color: t.muted, fontSize: font.sm }}>Box name</Text>
        <TextInput
          testID="box-name"
          style={input}
          value={form.box_name}
          onChangeText={(v) => setForm({ ...form, box_name: v.trim().toLowerCase() })}
          placeholder="home"
          placeholderTextColor={t.subtle}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Text style={{ color: t.muted, fontSize: font.sm }}>Time zone</Text>
        <TextInput
          testID="time-zone"
          style={input}
          value={form.time_zone}
          onChangeText={(v) => setForm({ ...form, time_zone: v.trim() })}
          placeholder="Europe/Berlin"
          placeholderTextColor={t.subtle}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Text style={{ color: t.muted, fontSize: font.sm }}>Where backups should go</Text>
        <View style={s.wrap}>
          {CHOICES.map((c) => (
            <Pressable
              key={c.id}
              testID={`choice-${c.id}`}
              accessibilityRole="radio"
              accessibilityState={{ selected: form.backup_choice === c.id }}
              onPress={() => setForm({ ...form, backup_choice: c.id, backup_destination_id: null })}
              style={[s.badge, { backgroundColor: form.backup_choice === c.id ? t.accent : t.card, borderColor: t.borderStrong, paddingVertical: space.sm }]}
            >
              <Text style={{ color: form.backup_choice === c.id ? t.accentText : t.text, fontSize: font.sm }}>{c.label}</Text>
            </Pressable>
          ))}
        </View>
        {form.backup_choice !== 'later' &&
          (options.length === 0 ? (
            <P muted small>No matching destination exists yet. Add one on the dashboard; it needs an owner's approval.</P>
          ) : (
            <View style={s.wrap}>
              {options.map((d) => (
                <Pressable
                  key={d.id}
                  testID={`dest-${d.id}`}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: form.backup_destination_id === d.id }}
                  onPress={() => setForm({ ...form, backup_destination_id: form.backup_destination_id === d.id ? null : d.id })}
                  style={[s.badge, { backgroundColor: form.backup_destination_id === d.id ? t.accentSoft : t.card, borderColor: t.borderStrong, paddingVertical: space.sm }]}
                >
                  <Text style={{ color: t.text, fontSize: font.sm }}>{d.label}</Text>
                </Pressable>
              ))}
            </View>
          ))}
        <P muted small>
          The name and zone are labels for the box's software. Choosing a backup place is only a preference: it does not
          start backups, add a destination or issue a recovery kit.
        </P>
        {problem ? <Notice tone="warn" text={problem} /> : null}
        {msg ? <Notice tone={msg.tone} text={msg.text} /> : null}
        <View style={s.wrap}>
          <Button testID="save-box-settings" label={busy ? 'Saving…' : 'Save'} disabled={busy || !!problem} onPress={() => void save()} />
        </View>
      </Card>
    </>
  );
}
