// SPDX-License-Identifier: Apache-2.0
// People (§12.6 users, FAM-01 family limits). Owner only. Roles are Owner, Adult, Teen, Child and Guest. The hub
// enforces who may do what and asks for a fresh passkey on every write (`step_up_required`); the phone only
// avoids offering what will be refused. Each change asks twice and names what it does. Limits (age rating, allowed
// apps, hours) are read here and edited on the dashboard.
import { useState } from 'react';
import { Pressable, Share, Text, TextInput, View } from 'react-native';
import { OP } from '../api/client';
import type { CreatedUser, FamilyProfile, UserInfo } from '../api/types';
import { requestError } from '../lib/manage';
import { asksParent, limitsText, ROLE_TEXT, ROLES, roleLabel } from '../lib/people';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H1, H2, Loading, Notice, P, Screen, s } from '../ui/bits';
import { font, radiusControl, space, useTheme } from '../ui/theme';

function RoleChips({ value, onPick, testPrefix }: { value: string; onPick: (r: string) => void; testPrefix: string }) {
  const t = useTheme();
  return (
    <View style={s.wrap}>
      {ROLES.filter((r) => r !== 'owner').map((r) => (
        <Pressable
          key={r}
          testID={`${testPrefix}-${r}`}
          accessibilityRole="button"
          accessibilityState={{ selected: value === r }}
          onPress={() => onPick(r)}
          style={{ paddingVertical: 6, paddingHorizontal: 12, borderRadius: radiusControl, borderWidth: 1, borderColor: value === r ? t.accent : t.borderStrong, backgroundColor: value === r ? t.accent : t.card }}
        >
          <Text style={{ color: value === r ? t.accentText : t.text, fontSize: font.sm, fontWeight: font.semibold }}>{roleLabel(r)}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function PeopleScreen() {
  const t = useTheme();
  const { api, features, principal } = useSignedIn();
  const users = useLoad(() => api.users(), [api]);
  const withLimits = features.has(OP.familyProfile);
  const limits = useLoad(async () => {
    const out: Record<string, FamilyProfile> = {};
    if (!withLimits) return out;
    for (const u of (await api.users()).filter((x) => asksParent(x.role)))
      out[u.id] = await api.familyProfile(u.id).catch(() => ({}) as FamilyProfile);
    return out;
  }, [api, withLimits]);
  const [pick, setPick] = useState<{ id: string; role: string }>();
  const [name, setName] = useState('');
  const [newRole, setNewRole] = useState('adult');
  const [armed, setArmed] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [invite, setInvite] = useState<{ who: string; url: string; code: string; expires?: string }>();
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' }>();

  if (users.loading) return <Loading what="people" />;
  const isOwner = principal?.role === 'owner';
  const mayWrite = isOwner && features.has(OP.usersUpdate);

  async function run(key: string, fn: () => Promise<unknown>, done: string, what: string) {
    if (armed !== key) return setArmed(key);
    setArmed(undefined);
    setBusy(true);
    setMsg(undefined);
    try {
      const out = await fn();
      const ot = (out as CreatedUser | undefined)?.one_time;
      if (ot?.enrolment_code) setInvite({ who: (out as CreatedUser).display_name, url: ot.enrolment_url, code: ot.enrolment_code, expires: ot.expires_at });
      setMsg({ text: done, tone: 'ok' });
      setPick(undefined);
      setName('');
      await Promise.all([users.reload(), limits.reload()]);
    } catch (e) {
      setMsg({ text: requestError(e, what).text, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  const list = users.data ?? [];
  return (
    <Screen testID="people">
      <H1>People</H1>
      <P muted small>Who can use this box, and as what. Role changes are made by an owner and need a fresh passkey on the hub.</P>
      {users.error && !users.data ? <Notice tone={users.forbidden ? 'warn' : 'bad'} text={users.forbidden ? 'Only an owner can see people.' : `Could not read people: ${users.error.message}`} /> : null}
      {list.map((u: UserInfo) => {
        const changing = pick?.id === u.id && pick.role !== u.role;
        return (
          <Card key={u.id} testID={`person-${u.id}`}>
            <View style={s.row}>
              <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold, flexShrink: 1 }}>{u.display_name}</Text>
              <View style={s.wrap}>
                <Badge label={roleLabel(u.role)} tone={u.role === 'owner' ? 'info' : 'neutral'} />
                {u.disabled ? <Badge label="disabled" tone="warn" /> : null}
              </View>
            </View>
            {asksParent(u.role) ? <P muted small>{limitsText(limits.data?.[u.id])}{withLimits ? ' Limits are edited on the dashboard.' : ''}</P> : null}
            {mayWrite && u.role !== 'owner' && (
              <>
                <RoleChips testPrefix={`role-${u.id}`} value={pick?.id === u.id ? pick.role : u.role} onPick={(r) => { setArmed(undefined); setPick({ id: u.id, role: r }); }} />
                {changing && (
                  <>
                    <P muted small>{ROLE_TEXT[pick!.role as keyof typeof ROLE_TEXT]}</P>
                    <Button
                      testID={`role-save-${u.id}`}
                      label={armed === `r-${u.id}` ? `Tap again: make ${u.display_name} ${roleLabel(pick!.role)}` : 'Change role'}
                      disabled={busy}
                      onPress={() => void run(`r-${u.id}`, () => api.setUserRole(u.id, pick!.role), `${u.display_name} is now ${roleLabel(pick!.role)}.`, 'that role change')}
                    />
                  </>
                )}
              </>
            )}
          </Card>
        );
      })}
      {mayWrite && features.has(OP.usersCreate) && (
        <>
          <H2>Add a person</H2>
          <Card testID="add-person">
            <TextInput
              testID="new-name"
              value={name}
              onChangeText={(v) => { setArmed(undefined); setName(v); }}
              placeholder="Name"
              placeholderTextColor={t.subtle}
              maxLength={100}
              style={{ color: t.text, borderColor: t.borderStrong, borderWidth: 1, borderRadius: radiusControl, padding: space.sm, fontSize: font.md }}
            />
            <RoleChips testPrefix="new-role" value={newRole} onPick={(r) => { setArmed(undefined); setNewRole(r); }} />
            <P muted small>{ROLE_TEXT[newRole as keyof typeof ROLE_TEXT]}</P>
            <Button
              testID="add"
              label={armed === 'add' ? `Tap again: add ${name.trim()} as ${roleLabel(newRole)}` : 'Add person'}
              disabled={busy || !name.trim()}
              onPress={() => void run('add', () => api.createUser({ display_name: name.trim(), role: newRole }), `${name.trim()} was added. Give them the sign-in link below now; it is shown only once.`, 'adding a person')}
            />
          </Card>
        </>
      )}
      {!isOwner && <P muted small>Only an owner can change people.</P>}
      {invite && (
        <Card testID="invite">
          <H2>{`Sign-in for ${invite.who}`}</H2>
          <P small>This link is shown only once and the hub cannot issue it again. Send it to {invite.who} now.{invite.expires ? ` It expires ${invite.expires}.` : ''}</P>
          <Text selectable testID="invite-url" style={{ color: t.text, fontSize: font.sm }}>{invite.url}</Text>
          <Text selectable testID="invite-code" style={{ color: t.text, fontSize: font.sm }}>{`Code: ${invite.code}`}</Text>
          <Button testID="invite-share" label="Copy or share" onPress={() => void Share.share({ message: invite.url })} />
          <Button testID="invite-done" label="I have sent it" onPress={() => setInvite(undefined)} />
        </Card>
      )}
      {msg && <Notice tone={msg.tone} text={msg.text} />}
    </Screen>
  );
}
