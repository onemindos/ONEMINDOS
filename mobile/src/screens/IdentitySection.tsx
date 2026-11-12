// SPDX-License-Identifier: Apache-2.0
// Settings → You: who the hub says you are (§12.6 /v1/me) and passkeys on this phone.
import { useState } from 'react';
import { View } from 'react-native';
import { OP } from '../api/client';
import { ApiError } from '../api/types';
import { platformPasskeys } from '../lib/passkeys';
import { creationOptionsFrom, PasskeyError, passkeyMessage, rpIdFor } from '../lib/webauthn';
import { useSignedIn } from '../session';
import { Button, Card, H2, Notice, P, Row, s } from '../ui/bits';

export function IdentitySection({ deviceName }: { deviceName: string }) {
  const { api, me, principal, features, connection, canDecide, refreshIdentity } = useSignedIn();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>();
  const hubUrl = connection.mode === 'live' ? connection.hubUrl : undefined;
  const canRegister = features.has(OP.passkeyRegisterOptions) && principal?.kind === 'person';
  const passkeys = platformPasskeys();

  async function addPasskey() {
    setBusy(true);
    setMsg(undefined);
    try {
      if (!passkeys?.supported()) throw new PasskeyError('not_supported', 'no platform authenticator');
      const opts = await api.passkeyRegisterOptions();
      const webauthn = await passkeys.create(creationOptionsFrom(opts, rpIdFor(hubUrl)));
      const r = await api.passkeyRegister({ credential: webauthn, label: deviceName });
      setMsg({ text: `Passkey "${r.label}" added. Approvals from this phone now use it.`, ok: true });
      await refreshIdentity();
    } catch (e) {
      const text =
        e instanceof PasskeyError
          ? passkeyMessage(e, rpIdFor(hubUrl)).replace('Nothing was approved or changed.', 'No passkey was added.')
          : e instanceof ApiError
            ? `The hub refused: ${e.message}`
            : String(e);
      setMsg({ text, ok: false });
    } finally {
      setBusy(false);
    }
  }

  const who = me?.principal.display_name ?? principal?.id;
  const signIn =
    connection.mode === 'mock' ? 'demo' : connection.auth === 'passkey' ? 'passkey (renews itself)' : 'access token (v0)';
  return (
    <>
      <H2>You</H2>
      <Card testID="identity">
        <Row label="You are" value={principal ? `${who} (${principal.role}${principal.kind !== 'person' ? `, ${principal.kind}` : ''})` : 'known to the hub only'} />
        <Row label="Can approve" value={canDecide === 'yes' ? 'yes' : canDecide === 'no' ? 'no' : 'the hub decides when you try'} />
        <Row label="Signed in with" value={signIn} />
        {me && <Row label="Passkeys on your account" value={String(me.passkeys)} />}
        {!features.has(OP.me) && connection.mode === 'live' && (
          <P muted small>This hub has no "who am I" route yet, so the app learns your role from the hub's answers.</P>
        )}
        {canRegister && (
          <>
            <P muted small>
              A passkey lives in this phone's secure hardware and is unlocked with Face ID, your fingerprint or your screen lock.
              Once you have one, every approval asks for it (decision F-2).
            </P>
            {msg && <Notice tone={msg.ok ? 'ok' : 'bad'} text={msg.text} />}
            <View style={s.wrap}>
              <Button testID="add-passkey" variant="secondary" label={busy ? 'Adding…' : 'Add a passkey on this phone'} disabled={busy} onPress={() => void addPasskey()} />
            </View>
          </>
        )}
      </Card>
    </>
  );
}
