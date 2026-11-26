// SPDX-License-Identifier: Apache-2.0
// "Approve and remember" (gateway permissions design §3.6.1, fix 4; PR 12 on the gateway).
//
// 1. The person picks a lifetime (30 days preselected, 90, 180 or Forever), "end if unused for 14 days"
//    (on), a daily limit, how they are told about uses, and which of this request's details may differ.
// 2. POST /v1/actions/{id}/approve-options with those choices: the gateway builds the narrowest rule,
//    binds its hash into the passkey challenge and writes the summary shown here (never this page's text).
// 3. The passkey signs; POST /v1/actions/{id}/approve sends the assertion with the rule exactly as the
//    gateway returned it. A changed rule is refused (rule_changed), and so is remembering without a passkey.
// The gateway also refuses what may not be remembered (physical, tainted, above write, hard-floor items,
// a requester on Locked or Always ask, anything needing a proven key it cannot check yet) and says why.
import { useState } from 'react';
import { Button, Dialog, type ActionSummary } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import { explain, read, usePermSdk } from '../../lib/permissions';
import { getPasskey, webauthnSupported } from '../../lib/webauthn';

type Choice = components['schemas']['RememberChoice'];
type Challenge = components['schemas']['ApprovalChallenge'];
type ApproveBody = components['schemas']['onemind_core__routers__actions__ApproveBody'];
interface Bound { rule: Record<string, unknown>; summary: string; required_level?: string }

const LIFETIMES: Array<[NonNullable<Choice['lifetime']>, string]> = [['30d', '30 days'], ['90d', '90 days'], ['180d', '180 days'], ['forever', 'Forever']];
const NOTICES: Array<[NonNullable<Choice['notify_after']>, string]> = [['digest', 'In my daily summary'], ['each', 'Every time'], ['silent', 'Never (read-only requests only)']];

export function RememberSheet({ action, onClose, onDone, sign = getPasskey }: {
  action: ActionSummary; onClose: () => void; onDone: (policyId?: string) => void;
  /** Test seam; the browser's WebAuthn by default. */ sign?: (publicKey: Record<string, unknown>) => Promise<Record<string, unknown>>;
}) {
  const sdk = usePermSdk();
  const [choice, setChoice] = useState<Choice>({ lifetime: '30d', lapse_unused: true, per_day: 10, notify_after: 'digest', unpin: [] });
  const [challenge, setChallenge] = useState<Challenge>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const params = Object.keys(action.params ?? {}).sort();
  const pick = (next: Partial<Choice>) => {
    setChoice({ ...choice, ...next });
    setChallenge(undefined); // a changed rule needs a new challenge: the passkey signs exactly what is shown
    setError(undefined);
  };
  const path = `/v1/actions/${encodeURIComponent(action.id)}`;
  const preview = async () => {
    setBusy(true);
    setError(undefined);
    try {
      setChallenge(await read(sdk.call<Challenge>({ method: 'POST', path: `${path}/approve-options`, body: { remember: choice } })));
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  };
  const bound = challenge?.remember as Bound | null | undefined;
  const approve = async () => {
    if (!challenge || !bound) return;
    setBusy(true);
    setError(undefined);
    try {
      const webauthn = await sign(challenge.publicKey);
      const body: ApproveBody = { webauthn, remember: { rule: bound.rule }, ...(challenge.plan_sha256 ? { plan_sha256: challenge.plan_sha256 } : {}) };
      // Never retried: a consumed passkey assertion is single use.
      const out = await read(sdk.call<{ remembered_policy?: string }>({ method: 'POST', path: `${path}/approve`, body, retry: false }));
      onDone(out?.remembered_policy);
    } catch (e) {
      setError(explain(e));
      setChallenge(undefined);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open role="alertdialog" size="lg" title="Approve and remember" onClose={() => (busy ? undefined : onClose())}
      description="Approve this request and let requests like it go through without asking, within the limits you set. You can see and revoke the rule under Settings, Permissions, Rules."
      actions={<>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        {bound
          ? <Button variant="primary" busy={busy} onClick={() => void approve()}>Approve and remember with passkey</Button>
          : <Button variant="primary" busy={busy} onClick={() => void preview()}>Show the rule</Button>}
      </>}>
      {!webauthnSupported() && <p className="om-note om-tone-warn" role="status">This needs your passkey, and this browser cannot use one.</p>}
      <fieldset>
        <legend>How long</legend>
        {LIFETIMES.map(([v, label]) => (
          <label key={v}><input type="radio" name="remember-life" checked={choice.lifetime === v} onChange={() => pick({ lifetime: v })} /> {label}</label>
        ))}
      </fieldset>
      {choice.lifetime === 'forever' && (
        <p className="om-note om-tone-warn">This rule never ends by itself. You can see it under Rules and end it with one tap. OneMind reminds you about it every 90 days.</p>
      )}
      <label><input type="checkbox" checked={choice.lapse_unused ?? true} onChange={(e) => pick({ lapse_unused: e.target.checked })} /> End if unused for 14 days</label>
      <label>At most this many a day <input type="number" min={1} max={1000} value={choice.per_day ?? 10} onChange={(e) => pick({ per_day: Math.max(1, Number(e.target.value) || 1) })} /></label>
      <label>Tell me when it is used
        <select value={choice.notify_after ?? 'digest'} onChange={(e) => pick({ notify_after: e.target.value as Choice['notify_after'] })}>
          {NOTICES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
      </label>
      {params.length > 0 && (
        <fieldset>
          <legend>Only for these details (untick one to allow any value)</legend>
          {params.map((k) => (
            <label key={k}>
              <input type="checkbox" checked={!(choice.unpin ?? []).includes(k)}
                onChange={(e) => pick({ unpin: e.target.checked ? (choice.unpin ?? []).filter((x) => x !== k) : [...(choice.unpin ?? []), k] })} />{' '}
              {k} = {String(action.params[k])}
            </label>
          ))}
        </fieldset>
      )}
      {bound && (
        <section aria-label="The rule your passkey will sign" className="om-note om-tone-info">
          <p><strong>The rule:</strong> {bound.summary}</p>
          <p className="om-hint">Written by your box from the rule itself. Your passkey signs exactly this rule; if anything changes you will be asked again.</p>
        </section>
      )}
      {error && <p className="om-note om-tone-bad" role="alert">{error}</p>}
    </Dialog>
  );
}
