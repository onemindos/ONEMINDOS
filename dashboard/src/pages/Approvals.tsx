// SPDX-License-Identifier: Apache-2.0
// Approvals: the queue of requests and the recent decisions. Approving is one loop (contract §12.4):
// the gateway's plan is shown as plain effects, an app that needs install secrets asks for them in a
// form sealed in this browser, a passkey signs the exact plan, and the gateway checks all of it.
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { ApprovalsBoard, Card, PageHeader, Button, Dialog, HoldToApprove, SecretsForm, actionTitle, sealValues, useToast, type ActionPlan, type ActionSummary, type AppSecrets, type SecretsSubmission, type SettingsLoadable, type VerificationLevel } from '@onemind/ui';
import { ApiError } from '../api/types';
import type { UserCreated } from '../api/wiring';
import { principalNamer, toActionPlan, toActionSummary } from '../data/adapters';
import { errorText, subjectOf, useHub } from '../data/hub';
import { t } from '../i18n';
import { PASSKEY_NOT_USED, PASSKEY_UNAVAILABLE, levelOf, type ApproveOpts } from '../lib/approve';
import { usePoll } from '../lib/hooks';
import { DesktopAppRequests } from './DesktopAppRequests';
import { webauthnSupported } from '../lib/webauthn';
import { useSignedIn } from '../session';
import { decideState } from '../shell/roles';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';
import { InviteDialog } from './InviteDialog';

/** Shown when the gateway computed no plan for a request. */
export const NO_PLAN_NOTE = 'The hub has not described what this request will change. Approve it only if you know what it does.';
export const APPROVE_HINT = 'Approving signs exactly this plan with your passkey. If the plan changes, the request has to be approved again.';

function planNote(a: ActionSummary): string {
  if (a.type === 'users.reinvite') return t('users.invite.replaceWarning');
  if (a.type === 'users.invite' && typeof a.params.role === 'string') {
    const note = t('users.invite.approval', { role: a.params.role });
    return typeof a.params.username === 'string' ? `${note} ${t('users.invite.username', { username: a.params.username })}` : note;
  }
  return NO_PLAN_NOTE;
}

export function Approvals() {
  const hub = useHub();
  const { api, mock } = useSignedIn();
  const { role } = useShell();
  // The role decides, not the token's scopes: an adult is refused by the gateway, so is never offered the buttons.
  const canDecide = decideState(role, hub.canDecide);
  const toast = useToast();
  const [params] = useSearchParams();
  const me = usePoll(() => api.me(), 0);
  const passkey = me.data?.step_up.passkeys_active === true && webauthnSupported();
  // Names for the people and agents on the cards. Only the owner may list them; for anyone else
  // (or if the hub does not answer) the cards fall back to the id, as before.
  const users = usePoll(() => api.users().catch(() => []), 0);
  const agents = usePoll(() => api.agents().catch(() => []), 0);
  const nameOf = principalNamer(users.data ?? [], agents.data ?? []);
  // D-028: the key level a request needs, once the hub has said so (approve-options' 409); the card shows it.
  const [levels, setLevels] = useState<Record<string, VerificationLevel>>({});
  const all = hub.actionList.map((a) => toActionSummary(a, hub.appName, nameOf)).map((a) => (levels[a.id] ? { ...a, required_level: levels[a.id] } : a));
  const waiting = all.filter((a) => a.state === 'awaiting_approval');
  const desktopInstalls = hub.actionList.filter((a) => a.state === 'awaiting_approval' && (a.type as string) === 'desktop.app.install' && typeof a.params.app_id === 'string').map((a) => a.params.app_id as string);
  const decided = all.filter((a) => a.state !== 'awaiting_approval' && a.state !== 'requested').slice(0, 10);
  const stale = hub.freshness === 'stale' || hub.freshness === 'offline';
  const actions: SettingsLoadable<ActionSummary[]> =
    hub.actions.data !== undefined
      ? { status: 'ready', data: waiting, asOf: hub.asOf ?? new Date().toISOString(), stale }
      : hub.actions.error
        ? { status: 'error', error: { error: hub.actions.error.code === 'network' ? 'unavailable' : (hub.actions.error.code as 'not_found'), message: hub.actions.error.message } }
        : { status: 'loading' };
  const plans: Record<string, SettingsLoadable<ActionPlan>> = {};
  for (const a of hub.actionList) {
    const plan = a.state === 'awaiting_approval' ? toActionPlan(a) : undefined;
    if (plan) plans[a.id] = { status: 'ready', data: plan, asOf: hub.asOf ?? new Date().toISOString(), stale };
  }

  // What the owner just decided, followed to its end. Written in words as a status line so the
  // outcome is announced even after the request leaves the waiting list.
  const [last, setLast] = useState<{ id: string; title: string }>();
  const [invite, setInvite] = useState<UserCreated>();
  const [practiceDone, setPracticeDone] = useState(false);
  const lastNow = last ? all.find((a) => a.id === last.id) : undefined;
  const ended = lastNow && !['requested', 'awaiting_approval', 'accepted', 'dispatched'].includes(lastNow.state);
  // The install secrets form, open for one request.
  const [form, setForm] = useState<{ action: ActionSummary; appId: string; name: string; secrets: AppSecrets; error?: string }>();
  const [sealing, setSealing] = useState(false);
  // #173: the gateway refused an install whose licence is not green until the owner types the app id.
  const [licence, setLicence] = useState<{ action: ActionSummary; appId: string; message: string; sealed?: ApproveOpts['sealed']; typed: string }>();

  // The gateway wants a passkey (a password sign-in cannot approve this). Ask for it with a button, which
  // also gives the browser the tap it needs to open the passkey prompt.
  const [stepUp, setStepUp] = useState<{ action: ActionSummary; sealed?: ApproveOpts['sealed']; acceptLicence?: string; hold?: ApproveOpts['hold']; busy: boolean }>();

  const fail = (how: string, e: unknown) => {
    const { code, message } = errorText(e);
    toast.show({ tone: 'bad', title: `Could not ${how}`, body: `${message} (${code})` });
  };
  const decide = (a: ActionSummary, how: 'approve' | 'deny', sealed?: ApproveOpts['sealed'], acceptLicence?: string, hold?: ApproveOpts['hold'], forcePasskey = false): Promise<boolean> =>
    hub.decide(a.id, how, { passkey: passkey || forcePasskey, sealed, acceptLicence, hold }).then(
      async (result) => {
        setLicence(undefined);
        setStepUp(undefined);
        setForm(undefined);
        setLast({ id: a.id, title: actionTitle(a) });
        if (how === 'approve' && (a.type === 'users.invite' || a.type === 'users.reinvite')) {
          if (result.state === 'succeeded' && api.claimInvite) {
            try { setInvite(await api.claimInvite(a.id)); }
            catch (e) { toast.show({ tone: 'bad', title: t('users.invite.claimError'), body: e instanceof Error ? e.message : String(e) }); }
          }
          return true;
        }
        toast.show({ tone: how === 'approve' ? 'ok' : 'neutral', title: how === 'approve' ? 'Approved' : 'Denied', body: how === 'approve' ? 'The hub is applying it. Progress shows on the app page and in the tray.' : 'Nothing changes.' });
        return true;
      },
      async (e: unknown) => {
        if (how === 'approve' && e instanceof ApiError && e.reason === 'licence_unconfirmed' && typeof a.params.app_id === 'string') {
          setStepUp(undefined);
          setForm(undefined);
          setLicence({ action: a, appId: a.params.app_id, message: e.message, sealed, typed: '' });
          return false;
        }
        const level = how === 'approve' ? levelOf(e) : undefined;
        if (level) setLevels((m) => ({ ...m, [a.id]: level }));
        // The hub needs a passkey and this browser cannot make one: say so in words, whatever the pass.
        if (how === 'approve' && e instanceof ApiError && e.reason === PASSKEY_UNAVAILABLE) {
          setStepUp(undefined);
          toast.show({ tone: 'bad', title: 'This approval needs a passkey', body: 'This browser cannot use a passkey. Open the dashboard in a browser that supports passkeys (on a secure https address) and approve again.' });
          return false;
        }
        // Only "the browser produced no passkey" opens the prompt. A step_up_required that reaches here means a
        // signed request was refused by the hub, so its own message is shown (fail below), not a false "not used".
        const needsPasskey = how === 'approve' && e instanceof ApiError && e.code === 'unauthenticated' && e.reason === PASSKEY_NOT_USED;
        if (needsPasskey && !forcePasskey) {
          setLicence(undefined);
          // This person's own passkey count decides (passkeys_active is true once any owner has one). When /v1/me
          // has not answered yet, ask it now rather than guess.
          const mine = me.data ?? await api.me().catch(() => undefined);
          if (mine && (mine.passkeys === 0 || mine.step_up.passkeys_active === false)) {
            toast.show({ tone: 'bad', title: 'This approval needs a passkey', body: 'You signed in with a password, and the hub needs a passkey to approve this. You have no passkey yet. Add one in Account and security, then sign in with it and approve again.' });
          } else {
            setStepUp({ action: a, sealed, acceptLicence, hold, busy: false });
          }
          return false;
        }
        if (needsPasskey) {
          toast.show({ tone: 'bad', title: 'Your passkey was not used', body: `Nothing was approved. Press Approve again and use your passkey when your device asks.` });
          setStepUp(undefined);
          return false;
        }
        setStepUp(undefined);
        fail(how, e);
        return false;
      },
    );

  const approve = async (a: ActionSummary, elapsedMs?: number) => {
    if (a.hold) {
      if (elapsedMs !== undefined && elapsedMs >= a.hold.duration)
        return decide(a, 'approve', undefined, undefined, { ms: elapsedMs, plan: a.hold.plan });
      return;
    }
    const appId = a.type === 'app.install' ? (a.params.app_id as string | undefined) : undefined;
    if (!appId || !api.appSecrets) return decide(a, 'approve');
    let secrets: AppSecrets;
    try {
      secrets = await api.appSecrets(appId);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'not_found') return decide(a, 'approve');
      return fail('approve', e);
    }
    // Only keys the owner types need a form; generated ones are made by the box.
    if (!secrets.secrets.some((s) => s.keys.some((k) => k.source === 'owner'))) return decide(a, 'approve');
    setForm({ action: a, appId, name: hub.appName(appId), secrets });
  };

  const submitSecrets = async (sub: SecretsSubmission) => {
    if (!form || !api.secretsPublicKey) return;
    setSealing(true);
    try {
      const sealed = await sealValues(await api.secretsPublicKey(), form.appId, sub.values);
      if (await decide(form.action, 'approve', sealed)) setForm(undefined);
    } catch (e) {
      fail('approve', e);
    } finally {
      setSealing(false);
    }
  };

  // A guest, child or teen is never offered Approvals, and a link here gets a calm line, not the gateway's error.
  if (role === 'guest' || role === 'child' || role === 'teen') {
    return (
      <div className="dash-stack">
        <PageHeader title="Approvals" />
        <Card variant="sunken">
          <p role="status">{t('approvals.ownerOnly')}</p>
          <p><Link to={href.home}>{t('approvals.backHome')}</Link></p>
        </Card>
      </div>
    );
  }
  return (
    <>
      {last && lastNow && (
        <p className="om-note om-tone-info" {...(ended ? { role: 'status' } : {})}>
          {last.title}: {ended ? lastNow.state.replace(/_/g, ' ') : 'approved, the hub is applying it'}.
        </p>
      )}
    <ApprovalsBoard
      actions={actions}
      plans={plans}
      planNote={planNote}
      approveHint={passkey && me.data?.setup_pending === undefined ? APPROVE_HINT : `Approval applies to the plan shown here. Some actions ask you to verify your identity before the box applies the change.${passkey ? '' : ' Add a passkey in Account and security to have every approval signed.'}`}
      calls={['GET /v1/actions', 'POST /v1/actions/{id}/approve-options', 'POST /v1/actions/{id}/approve', 'POST /v1/actions/{id}/deny']}
      decided={decided}
      now={hub.now}
      canDecide={canDecide === 'yes' ? { allowed: true } : canDecide === 'unknown'
        ? { allowed: false, reason: 'Checking who you are…' }
        : { allowed: false, reason: 'Only the owner can approve or deny. Agents can ask and only a person can approve.' }}
      onApprove={(a, elapsedMs) => void approve(a, elapsedMs)}
      onDeny={(a) => void decide(a, 'deny')}
      onRetry={hub.reloadAll}
      initialId={params.get('highlight') ?? undefined}
      key={params.get('highlight') ?? ''}
    />
    {canDecide === 'yes' && (
      <section aria-labelledby="approval-practice-title">
        <h2 id="approval-practice-title">{t('approvals.practice.title')}</h2>
        <p>{practiceDone ? 'Practice approved.' : 'Try an approval without changing your box. Press and hold the button.'}</p>
        {practiceDone
          ? <Button onClick={() => setPracticeDone(false)}>{t('common.retry')}</Button>
          : <HoldToApprove label="Practice: Hold to approve" onApprove={() => setPracticeDone(true)} />}
      </section>
    )}
    {!mock && desktopInstalls.length > 0 && <DesktopAppRequests key={desktopInstalls.join(',')} appIds={desktopInstalls} />}
    {hub.actionList.filter((a) => a.state === 'awaiting_approval' && a.plan).map((a) => (
      <details key={a.id} className="om-hint">
        <summary>Advanced: raw plan for {a.type} {subjectOf(hub, a)}</summary>
        <pre>{JSON.stringify(a.plan, null, 2)}</pre>
        <p>Plan fingerprint: {a.plan_sha256}</p>
      </details>
    ))}
    {form && (
      <Dialog open title={`Secrets for ${form.name}`} description="Typed here, encrypted in this browser to your hub, and sent with your approval. They are never shown again." size="lg" onClose={() => (sealing || stepUp ? undefined : setForm(undefined))}>
        <SecretsForm app={{ id: form.appId, name: form.name }} secrets={form.secrets} mode="install" submitLabel="Approve and install" busy={sealing} error={form.error} onSubmit={(s) => void submitSecrets(s)} onCancel={() => setForm(undefined)} />
      </Dialog>
    )}
    {stepUp && (
      <Dialog
        open role="alertdialog" title="Use your passkey to approve"
        description="This approval needs your passkey, not just your password. Press the button, then use your passkey when your device asks. Nothing is approved until you do."
        onClose={() => (stepUp.busy ? undefined : setStepUp(undefined))}
        actions={<>
          <Button onClick={() => setStepUp(undefined)} disabled={stepUp.busy}>Cancel</Button>
          <Button variant="primary" disabled={stepUp.busy} onClick={() => {
            setStepUp({ ...stepUp, busy: true });
            void decide(stepUp.action, 'approve', stepUp.sealed, stepUp.acceptLicence, stepUp.hold, true);
          }}>{t('approvals.usePasskey')}</Button>
        </>}
      >
        <p>{actionTitle(stepUp.action)}</p>
      </Dialog>
    )}
    {licence && (
      <Dialog
        open role="alertdialog" title={`Accept the licence for ${hub.appName(licence.appId)}?`}
        description={`${licence.message}. This app's licence is not one the Market marks as safe to install without asking. Read it, then type the app id (${licence.appId}) to accept it.`}
        onClose={() => setLicence(undefined)}
        actions={<>
          <Button onClick={() => setLicence(undefined)}>Cancel</Button>
          <Button variant="primary" disabled={licence.typed !== licence.appId} onClick={() => void decide(licence.action, 'approve', licence.sealed, licence.appId)}>{t('approvals.licence.accept')}</Button>
        </>}
      >
        <label>{t('approvals.licence.appId')} <input aria-label={t('approvals.licence.appId')} value={licence.typed} autoComplete="off" onChange={(e) => setLicence({ ...licence, typed: e.target.value })} /></label>
      </Dialog>
    )}
    <InviteDialog invite={invite} onClose={() => setInvite(undefined)} />
    </>
  );
}
