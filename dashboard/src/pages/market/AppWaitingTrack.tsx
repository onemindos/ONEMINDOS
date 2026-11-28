// SPDX-License-Identifier: Apache-2.0
// Atlas app page, waiting (prototype 05; the phone's AppInstallWaiting, #1230): an install or update
// request for this app that waits for an owner. The track is read from the action itself (who asked,
// when, whether the hub computed a plan) and the catalog's scan record; nothing is assumed.
// Approving goes through hub.decide, the same passkey step-up Approvals uses (contract §12.4, D-027).
// Anything this card cannot finish on its own (a hold, owner-typed install secrets, a licence that
// must be accepted by typing the app id) sends the owner to the request in Approvals instead.
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Button, Icon, useToast } from '@onemind/ui';
import { ApiError, type Action, type CatalogApp } from '../../api/types';
import { appIdOf } from '../../data/adapters';
import { errorText, useHub } from '../../data/hub';
import { usePoll } from '../../lib/hooks';
import { formatAgo, formatIn, secondsSince } from '../../lib/time';
import { webauthnSupported } from '../../lib/webauthn';
import { useSignedIn } from '../../session';
import { href } from '../../shell/routes';
import { askedBy, ownsRequest, type Viewer } from './requests';
import './market.css';

type StepState = 'done' | 'current' | 'todo' | 'problem';
interface Step { title: string; detail: string; state: StepState }

/** The five steps of prototype 05, from what the hub sent. Exported for tests. */
export function waitingSteps(action: Action, app: Pick<CatalogApp, 'scan'> | undefined, now: number, me: Viewer, owner: boolean, passkey = false): Step[] {
  const update = action.type === 'app.update';
  const asked = action.created_at ? formatAgo(secondsSince(action.created_at, now)) : 'time not reported';
  const scan = app?.scan ? (app.scan.result === 'pass' ? 'Scan passed' : 'Scan failed') : 'Never scanned';
  const planned = !!action.plan_sha256 || !!action.plan;
  const w = (action.plan as { warnings?: unknown } | null | undefined)?.warnings;
  const warnings = Array.isArray(w) ? w.length : 0;
  return [
    { title: 'Requested', detail: `${askedBy(action, me) === 'you' ? 'You' : askedBy(action, me)} · ${asked}`, state: 'done' },
    {
      title: 'Plan checked',
      detail: planned ? `${scan}${warnings ? ` · ${warnings} warning${warnings === 1 ? '' : 's'}` : ''}` : 'The hub sent no plan',
      state: planned && app?.scan?.result !== 'fail' ? 'done' : 'problem',
    },
    { title: owner ? 'Your approval' : 'Owner approval', detail: `${passkey ? 'Passkey · ' : ''}${formatIn(action.expires_at, now) === 'expired' ? 'expired' : `ends ${formatIn(action.expires_at, now)}`}`, state: 'current' },
    { title: update ? 'Update' : 'Install', detail: 'After approval', state: 'todo' },
    { title: 'Running', detail: 'Opens from the Market', state: 'todo' },
  ];
}

export function AppWaitingTrack({ action, app }: { action: Action; app: CatalogApp | undefined }) {
  const hub = useHub();
  const { api, account, principal } = useSignedIn();
  const viewer = account ?? principal;
  const navigate = useNavigate();
  const toast = useToast();
  const [msg, setMsg] = useState<string>();
  const me = usePoll(() => api.me(), 0);
  const passkey = me.data?.step_up.passkeys_active === true && webauthnSupported();
  const owner = hub.canDecide === 'yes';
  const mine = ownsRequest(action, viewer);
  const expired = Date.parse(action.expires_at) <= hub.now;
  const stale = hub.freshness === 'stale' || hub.freshness === 'offline';
  const busy = hub.busy.has(action.id);
  const canAct = owner && !expired && !stale && !busy;
  const steps = waitingSteps(action, app, hub.now, viewer, owner, passkey);
  const name = app?.name || app?.id || 'this app';
  const toApprovals = (why: string) => {
    toast.show({ tone: 'neutral', title: 'Finish in Approvals', body: why });
    navigate(href.approval(action.id));
  };

  const approve = async () => {
    if (!canAct) return;
    setMsg(undefined);
    if (action.approval?.hold) return toApprovals('This request needs a hold to approve.');
    const appId = appIdOf(action);
    if (action.type === 'app.install' && appId && api.appSecrets) {
      try {
        const s = await api.appSecrets(appId);
        if (s.secrets.some((x) => x.keys.some((k) => k.source === 'owner'))) return toApprovals(`${name} needs values only you can type. Approvals seals them in this browser.`);
      } catch (e) {
        if (!(e instanceof ApiError && e.code === 'not_found')) return setMsg(errorText(e).message);
      }
    }
    try {
      await hub.decide(action.id, 'approve', { passkey });
      toast.show({ tone: 'ok', title: 'Approved', body: `The hub is installing ${name}. Progress shows here and in the tray.` });
    } catch (e) {
      if (e instanceof ApiError && e.reason === 'licence_unconfirmed') return toApprovals(`${name}'s licence has to be accepted by typing its id.`);
      setMsg(errorText(e).message);
    }
  };

  const deny = async () => {
    if (!canAct) return;
    setMsg(undefined);
    try {
      await hub.decide(action.id, 'deny');
      toast.show({ tone: 'neutral', title: mine ? 'Request cancelled' : 'Request denied', body: 'Nothing was installed or changed.' });
    } catch (e) {
      setMsg(errorText(e).message);
    }
  };

  const headId = `wait-${action.id}`;
  return (
    <section className="dash-mkt-wait" aria-labelledby={headId}>
      <h2 id={headId} className="dash-mkt-wait-title">
        <span className="dash-mkt-wait-mark" aria-hidden="true" />
        {mine ? 'You asked to install this. ' : ''}It waits for {owner ? 'your' : 'an owner’s'} approval.
      </h2>
      <p className="om-hint">Nothing has been downloaded or changed yet. Approving starts the {action.type === 'app.update' ? 'update' : 'install'} on the hub.</p>
      <ol className="dash-mkt-track" aria-label="Request progress">
        {steps.map((s) => (
          <li key={s.title} className={`dash-mkt-step dash-mkt-step-${s.state}`} aria-current={s.state === 'current' ? 'step' : undefined}>
            <span className="dash-mkt-step-dot" aria-hidden="true" />
            <strong>{s.title}</strong>
            <span className="om-visually-hidden">{s.state === 'done' ? ' (done)' : s.state === 'problem' ? ' (needs a look)' : s.state === 'current' ? ' (now)' : ' (next)'}</span>
            <span className="dash-mkt-step-detail">{s.detail}</span>
          </li>
        ))}
      </ol>
      {owner ? (
        <div className="dash-mkt-wait-actions">
          <Button variant="primary" disabled={!canAct} onClick={() => void approve()}>{passkey ? 'Approve with passkey' : 'Approve'}</Button>
          <a className="om-btn om-btn-secondary" href={href.approval(action.id)}>Review the plan</a>
          <Button disabled={!canAct} onClick={() => void deny()}>{mine ? 'Cancel request' : 'Deny'}</Button>
          <span className="dash-mkt-undo"><Icon name="check" size={16} /> Can be undone: remove the app later</span>
        </div>
      ) : (
        <p>An owner sees this request in Approvals and decides there. <a href={href.approval(action.id)}>See the request</a></p>
      )}
      {expired && <p className="om-note om-tone-warn" role="status">This request ran out of time. Ask again from this page.</p>}
      {stale && !expired && <p className="om-note om-tone-warn" role="status">The hub is not answering. Deciding waits until it is back.</p>}
      {msg && <p className="om-note om-tone-bad" role="alert">{msg}</p>}
      {owner && (
        <p className="dash-mkt-wait-foot">
          <span>{action.approval?.hold ? 'This one needs a hold, in Approvals.' : passkey ? 'A plain button, no hold: installing an app can be undone and moves nothing physical.' : 'Approving uses your sign-in. Add a passkey in Account and security to have every approval signed.'}</span>
          <code>onemind actions approve {action.id}</code>
        </p>
      )}
    </section>
  );
}
