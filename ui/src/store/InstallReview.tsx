// SPDX-License-Identifier: Apache-2.0
// Install review (TAXONOMY §4.6, IA §2.3, PU-06): one concern per step, generated from the app's
// facets and the hub's plan; steps that do not apply are skipped. The last step creates the
// request; nothing is installed until an owner approves it in Approvals (P1).
import { useState } from 'react';
import { Button } from '../components/Button';
import { Dialog } from '../components/Dialog';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { formatAgo, secondsSince } from '../lib/time';
import { AppTile, ClassPills, RequestDetails } from './bits';
import { apiEquivalent, buildRequest, cliEquivalent } from './logic';
import { DEVICE_LABEL, EXPOSURE_LABEL } from './taxonomy';
import type { AppPlan, CatalogApp, StoreActionRequest } from './types';

export type ReviewStep = 'community' | 'node' | 'devices' | 'network' | 'storage' | 'exposure' | 'review';

export const STEP_TITLE: Record<ReviewStep, string> = {
  community: 'Not fully checked',
  node: 'Where it runs',
  devices: 'Device access',
  network: 'Network',
  storage: 'Storage',
  exposure: 'Who can reach it',
  review: 'Review request',
};

/** Only the steps that apply, in the fixed order (TAXONOMY §4.6). */
export function reviewSteps(app: CatalogApp, plan?: AppPlan, noPlacement = false): ReviewStep[] {
  const s: ReviewStep[] = [];
  if (app.deploy_class === 'market-community') s.push('community');
  if (!noPlacement) s.push('node');
  if (app.placement?.devices?.length) s.push('devices');
  if (app.placement?.hostNetwork || plan?.host_ports?.length) s.push('network');
  if (app.storage?.data || plan?.volumes?.length) s.push('storage');
  if (app.placement?.exposure && app.placement.exposure !== 'lan') s.push('exposure');
  s.push('review');
  return s;
}

export interface InstallReviewProps {
  app: CatalogApp;
  /** The hub's plan; undefined while it loads. */
  plan?: AppPlan;
  planError?: string;
  open: boolean;
  now: number;
  onClose: () => void;
  onSubmit: (req: StoreActionRequest) => void;
  /**
   * The gateway serves no placement plan (contract v0): skip the node step, let the hub place
   * the app, and say so in this sentence on the review step.
   */
  placementNote?: string;
}

export function InstallReview({ app, plan, planError, open, now, onClose, onSubmit, placementNote }: InstallReviewProps) {
  const noPlacement = !!placementNote && !plan && !planError;
  const steps = reviewSteps(app, plan, noPlacement);
  const [i, setI] = useState(0);
  const [node, setNode] = useState<string | undefined>(undefined);
  const [ackCommunity, setAck] = useState(false);
  const step = steps[Math.min(i, steps.length - 1)]!;
  const fitting = plan?.nodes.filter((n) => n.fits) ?? [];
  const chosen = node ?? plan?.nodes.find((n) => n.chosen && n.fits)?.node ?? fitting[0]?.node;
  const req = buildRequest('app.install', app, chosen ? { node: chosen } : {});
  const blocked = !!planError || (plan && fitting.length === 0);
  const nextDisabled = (step === 'community' && !ackCommunity) || (step === 'node' && (!plan || blocked));
  const close = () => {
    setI(0);
    onClose();
  };

  const body = (() => {
    switch (step) {
      case 'community':
        return (
          <div className="om-store-review">
            <p>OneMind lists {app.name}, but it did not pass every Market check. These were not checked or did not pass:</p>
            <ul className="om-perm-list">
              {(app.community_gaps ?? ['Not recorded']).map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
            <label className="om-store-check">
              <input type="checkbox" checked={ackCommunity} onChange={(e) => setAck(e.target.checked)} />
              <span>I understand {app.name} is not fully checked by OneMind.</span>
            </label>
          </div>
        );
      case 'node':
        if (planError)
          return (
            <p className="om-note om-tone-bad" role="alert">
              Could not get a placement plan: {planError}
            </p>
          );
        if (!plan)
          return (
            <p role="status" className="om-hint">
              Asking the hub which nodes can run {app.name}…
            </p>
          );
        return (
          <fieldset className="om-store-nodes">
            <legend>The box picked the best node. You can change it to another node that fits.</legend>
            {plan.nodes.map((n) => (
              <label key={n.node} className="om-store-node" data-fits={n.fits}>
                <input type="radio" name="om-store-node" value={n.node} checked={chosen === n.node} disabled={!n.fits} onChange={() => setNode(n.node)} />
                <span className="om-store-node-main">
                  <strong>{n.node}</strong>
                  {n.chosen && <StatusPill tone="info" label="Suggested" dot={false} />}
                  {n.stale && <StatusPill tone="warn" label="Stale" detail={n.last_seen ? `last report ${formatAgo(secondsSince(n.last_seen, now))}` : undefined} />}
                  {!n.fits && <StatusPill tone="bad" label="Does not fit" />}
                  <span className="om-hint">{n.reasons.join(' · ')}</span>
                </span>
              </label>
            ))}
            {blocked && <p className="om-note om-tone-bad">No node can run {app.name}. Install cannot be requested.</p>}
          </fieldset>
        );
      case 'devices':
        return (
          <div className="om-store-review">
            <p>{app.name} needs access to hardware on the node. OneMind passes the device through; it never exposes a host path.</p>
            <ul className="om-perm-list">
              {app.placement!.devices!.map((d) => (
                <li key={d.class}>
                  {DEVICE_LABEL[d.class]} {d.required ? '(required)' : '(optional)'}
                </li>
              ))}
            </ul>
          </div>
        );
      case 'network':
        return (
          <div className="om-store-review">
            {app.placement?.hostNetwork && <p>Uses the node's network directly. This is needed for device discovery on your home network.</p>}
            {plan?.host_ports?.length ? <p>Opens these ports on the node: {plan.host_ports.join(', ')}.</p> : null}
          </div>
        );
      case 'storage':
        return (
          <div className="om-store-review">
            <ul className="om-perm-list">
              {(plan?.volumes ?? (app.storage?.data ? [{ name: 'data', size: app.storage.data.size, backup: app.storage.data.backup }] : [])).map((v) => (
                <li key={v.name}>
                  Keeps up to {v.size} in “{v.name}”, {v.backup ? 'backed up with the box' : 'not backed up'}.
                </li>
              ))}
            </ul>
            <p className="om-hint">Removing the app later keeps this data unless you ask to delete it.</p>
          </div>
        );
      case 'exposure':
        return (
          <div className="om-store-review">
            <p>After install it is reachable on {EXPOSURE_LABEL.lan}.</p>
            <p>
              It may later be opened to {EXPOSURE_LABEL[app.placement!.exposure!]}. That is never part of this install: it is a separate request you approve on its
              own.
            </p>
          </div>
        );
      case 'review':
        return (
          <div className="om-store-review">
            <dl className="om-facts">
              <div>
                <dt>App</dt>
                <dd>
                  {app.name} {app.version}
                </dd>
              </div>
              <div>
                <dt>Node</dt>
                <dd>{noPlacement ? placementNote : (chosen ?? 'none fits')}</dd>
              </div>
              <div>
                <dt>Expires</dt>
                <dd>in 24 h if nobody decides</dd>
              </div>
            </dl>
            {app.permissions?.length ? (
              <>
                <h3 className="om-subhead">It will be able to</h3>
                <ul className="om-perm-list">
                  {app.permissions.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </>
            ) : null}
            {app.plugin && (
              <>
                <h3 className="om-subhead">It adds to OneMind</h3>
                <ul className="om-perm-list">
                  {(app.extensions ?? []).map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                  {plan?.agent_scopes?.length ? <li>Can ask for actions ({plan.agent_scopes.join(', ')}); you approve each one</li> : null}
                </ul>
              </>
            )}
            <RequestDetails api={apiEquivalent(req)} cli={cliEquivalent(req)} proposed={false} />
          </div>
        );
    }
  })();

  const last = i >= steps.length - 1;
  return (
    <Dialog
      open={open}
      onClose={close}
      title={`Request install: ${app.name}`}
      size="md"
      description={
        <div className="om-store-review-head">
          <AppTile app={app} size={40} />
          <div>
            <p>
              Step {Math.min(i, steps.length - 1) + 1} of {steps.length}: <strong>{STEP_TITLE[step]}</strong>
            </p>
            <ClassPills app={app} />
          </div>
        </div>
      }
      actions={
        <>
          {i > 0 ? (
            <Button onClick={() => setI(i - 1)}>Back</Button>
          ) : (
            <Button onClick={close}>Cancel</Button>
          )}
          {last ? (
            <Button
              variant="primary"
              disabled={(!chosen && !noPlacement) || blocked}
              onClick={() => {
                onSubmit(req);
                close();
              }}
            >
              <Icon name="approvals" size={18} />
              Send request
            </Button>
          ) : (
            <Button variant="primary" disabled={nextDisabled} onClick={() => setI(i + 1)}>
              Next
            </Button>
          )}
        </>
      }
    >
      <ol className="om-store-dots" aria-hidden="true">
        {steps.map((s, k) => (
          <li key={s} className={k <= i ? 'om-store-dot-on' : undefined} />
        ))}
      </ol>
      {body}
    </Dialog>
  );
}
