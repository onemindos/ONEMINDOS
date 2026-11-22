// SPDX-License-Identifier: Apache-2.0
// Approvals screen: set up or remove this phone's approval key (#703), and the hook the screen signs with.
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ApprovalKeyNative } from '../../modules/onemind-approval-key';
import { OP, type Features, type OneMindApi } from '../api/client';
import { ApiError } from '../api/types';
import { deviceInfo } from '../lib/device';
import { Button, Card, H2, Notice, P, Row } from '../ui/bits';
import { ApprovalKeyError, approvalKeyMessage, enrol, forget, loadRecord, makeSigner, type ApprovalKeyRecord, type ApprovalSigner } from '.';

export interface ApprovalKeyState {
  /** undefined while loading; null when this phone has no key for this hub. */
  rec: ApprovalKeyRecord | null | undefined;
  signer?: ApprovalSigner;
  set(rec: ApprovalKeyRecord | null): void;
}

export function useApprovalKey(native: ApprovalKeyNative | undefined, hubUrl: string | undefined): ApprovalKeyState {
  const [rec, set] = useState<ApprovalKeyRecord | null>();
  useEffect(() => {
    let live = true;
    void (async () => {
      let r = native && hubUrl ? await loadRecord(hubUrl) : null;
      // The Keystore deleted the key (a new enrolment, or the app's data was cleared): it cannot sign.
      if (r && native && native.status().publicKey !== r.publicKey) r = null;
      if (live) set(r);
    })();
    return () => {
      live = false;
    };
  }, [native, hubUrl]);
  const signer = useMemo(() => (rec && native ? makeSigner(rec, native) : undefined), [rec, native]);
  return { rec, signer, set };
}

const WHERE: Record<ApprovalKeyRecord['securityLevel'], string> = {
  strongbox: 'StrongBox secure chip',
  tee: 'secure hardware',
  software: 'app storage (no secure hardware on this phone)',
};

function errText(e: unknown): string {
  if (e instanceof ApprovalKeyError) return approvalKeyMessage(e);
  if (e instanceof ApiError && e.reason === 'step_up_required')
    return 'The hub needs a fresh passkey sign-in on this phone first. Sign out, sign in with your passkey, then set up the key.';
  if (e instanceof ApiError) return `The hub refused: ${e.message}`;
  return String(e);
}

export function ApprovalKeySection({
  api,
  features,
  native,
  hubUrl,
  state,
  owner,
}: {
  api: OneMindApi;
  features: Features;
  native: ApprovalKeyNative | undefined;
  hubUrl: string | undefined;
  state: ApprovalKeyState;
  owner: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>();
  const run = useCallback(
    async (what: () => Promise<string>) => {
      setBusy(true);
      setMsg(undefined);
      try {
        setMsg({ text: await what(), ok: true });
      } catch (e) {
        setMsg({ text: errText(e), ok: false });
      }
      setBusy(false);
    },
    [],
  );
  if (!native || !hubUrl || !owner || !features.has(OP.approverKeys) || state.rec === undefined) return null;
  const rec = state.rec;
  return (
    <Card testID="approval-key">
      <H2>Approval key on this phone</H2>
      {rec ? (
        <>
          <Row label="Kept in" value={WHERE[rec.securityLevel]} />
          <P muted small>Every approval asks for your fingerprint or face and signs the exact plan. A PIN or pattern is never accepted. Adding a new fingerprint or face turns the key off until you set it up again.</P>
          <Button
            testID="approval-key-remove"
            label="Remove approval key"
            variant="secondary"
            disabled={busy}
            onPress={() =>
              void run(async () => {
                await forget(api, rec, native);
                state.set(null);
                return 'Approval key removed from this phone and the hub.';
              })
            }
          />
        </>
      ) : (
        <>
          <P muted small>Approve with your fingerprint or face: a key in this phone's secure hardware signs each plan you approve. The hub keeps only the public half.</P>
          <Button
            testID="approval-key-setup"
            label="Set up approval key"
            disabled={busy}
            onPress={() =>
              void run(async () => {
                state.set(await enrol(api, hubUrl, deviceInfo('').name, native));
                return 'Approval key set up. Approvals now ask for your fingerprint or face.';
              })
            }
          />
        </>
      )}
      {msg && <Notice tone={msg.ok ? 'ok' : 'bad'} text={msg.text} />}
    </Card>
  );
}
