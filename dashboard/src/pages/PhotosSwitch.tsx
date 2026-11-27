// SPDX-License-Identifier: Apache-2.0
// Settings > Apps, "Photos": the switch for the built-in Photos app (refs #1232, #234). Photos is on by
// default. GET /v1/settings/photos tells the state; PUT files an app.enable or app.disable request that
// waits in Approvals: nothing changes until an owner approves it there. Through @onemind/sdk. The same
// switch is `onemind photos settings` on the CLI.
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Card, StatusPill, useToast } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useGateway } from '../lib/gateway';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load, useRun } from './parts';

export interface PhotosSwitch {
  enabled: boolean; owner_switch_on: boolean; operator_off: boolean; can_change: boolean; pending_action_id: string | null;
}

function fail(e: unknown): never {
  if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : e.status === 404 ? 'not_found' : 'unknown', e.message, e.reason);
  throw new ApiError(0, 'unknown', String(e));
}

/** GET /v1/settings/photos, checked: a malformed answer is an error, never a half-drawn switch. */
export async function readPhotosSwitch(client: OneMind): Promise<PhotosSwitch> {
  let v: unknown;
  try { v = await client.call<unknown>({ method: 'GET', path: '/v1/settings/photos' }); } catch (e) { fail(e); }
  const x = v as Record<string, unknown> | null;
  if (!x || typeof x.enabled !== 'boolean' || typeof x.owner_switch_on !== 'boolean' || typeof x.operator_off !== 'boolean'
    || typeof x.can_change !== 'boolean' || !(x.pending_action_id === null || typeof x.pending_action_id === 'string')) {
    throw new ApiError(200, 'unknown', 'The hub returned an invalid Photos switch.');
  }
  return x as unknown as PhotosSwitch;
}

export function PhotosSwitchCard() {
  const { token, mock } = useSignedIn();
  if (mock) return null;
  return <LivePhotos token={token} />;
}

function LivePhotos({ token }: { token: string }) {
  const client = useGateway(token);
  const run = useRun();
  const toast = useToast();
  const navigate = useNavigate();
  const hub = useHub();
  const isOwner = hub.canDecide === 'yes'; // the API refuses everyone else (403): offer the switch to an owner only
  const state = usePoll(() => readPhotosSwitch(client), 30_000);
  const [busy, setBusy] = useState(false);

  async function set(enabled: boolean) {
    setBusy(true);
    try {
      const action = await run(async () => {
        try { return await client.call<{ id: string }>({ method: 'PUT', path: '/v1/settings/photos', body: { enabled } }); } catch (e) { return fail(e); }
      }, enabled ? 'Could not ask to switch Photos on' : 'Could not ask to switch Photos off');
      if (!action) return;
      toast.show({ tone: 'info', title: 'Request sent', body: 'It waits in Approvals until an owner decides. Nothing changes before that.' });
      void hub.actions.reload();
      navigate(href.approval(action.id));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card as="section" title="Photos" subtitle="Phone photo backup and the photo library. On by default.">
      <Load res={state} what="Reading the Photos switch">{(s) => (
        <>
          <p className="dash-row">
            <StatusPill tone={s.enabled ? 'ok' : 'neutral'} label={s.enabled ? 'On' : 'Off'} />{' '}
            {s.operator_off
              ? <span className="om-hint">Switched off in the box's configuration; an operator has to change that.</span>
              : isOwner && s.can_change && (
                <>
                  <button type="button" role="switch" className="om-set-switch" aria-checked={s.owner_switch_on} aria-label={`Photos: ${s.owner_switch_on ? 'on' : 'off'}`}
                    disabled={busy || s.pending_action_id !== null} onClick={() => void set(!s.owner_switch_on)}>
                    <span className="om-set-switch-thumb" aria-hidden="true" />
                  </button>{' '}
                  {s.pending_action_id !== null
                    ? <span role="status">Waiting for approval</span>
                    : <span className="om-hint">{s.owner_switch_on ? 'Switch off (keeps your photos)' : 'Switch back on'}</span>}
                </>
              )}
          </p>
          {!isOwner && <p className="om-hint">Only an owner can change this.</p>}
          <p className="om-hint">Changing it is an owner approval. On the box: <code>onemind photos settings</code>.</p>
        </>
      )}</Load>
    </Card>
  );
}
