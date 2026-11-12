// SPDX-License-Identifier: Apache-2.0
// Installed apps: open, and remove (a request; data kept by default). Restart, stop, update,
// settings and logs are drawn by @onemind/ui but are not in contract v0, so they say which stream
// brings them and never send anything.
import { useNavigate, useParams } from 'react-router';
import { InstalledList, ManageApp, PageHeader, useToast, type InstalledApp, type StoreActionRequest } from '@onemind/ui';
import { toInstalled, toJob } from '../data/adapters';
import { useHub } from '../data/hub';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';
import { loadState, StoreTabs } from './Market';

/**
 * Honest note on removal (contract v0): the gateway's executor deletes the app's namespace, so
 * whether the data volume survives depends on its storage class. Keep-data removal
 * (`app.remove` with `delete_data: false`) is §12.5.
 */
export const REMOVE_NOTE =
  'Removing asks the owner first. On this hub version the app’s namespace is deleted on removal; its data survives only where the storage keeps released volumes. Guaranteed keep-data removal comes with §12.5.';

export function Installed() {
  const hub = useHub();
  const shell = useShell();
  const toast = useToast();
  const navigate = useNavigate();
  const { appId } = useParams();
  const state = loadState(hub.apps, hub);
  const checkedAt = hub.asOf ?? new Date(0).toISOString();
  const installed: InstalledApp[] = (hub.apps.data ?? []).filter((a) => a.installed || a.status === 'removing').map((a) => toInstalled(a, checkedAt));
  const jobs = hub.actionList.map((a) => toJob(a, hub.appName(a.params.app_id)));

  const onOpen = (inst: InstalledApp) => {
    if (inst.url) window.open(inst.url, '_blank', 'noopener');
  };
  const onRequest = (req: StoreActionRequest) => {
    if (req.type === 'app.remove') {
      if (req.params.keep_data === false) {
        toast.show({ tone: 'neutral', title: 'Not sent', body: 'Deleting an app’s data with the removal comes with §12.5. Remove it (data kept) instead.' });
        return;
      }
      void shell.requestApp('app.remove', req.params.app_id).then((id) => id && navigate(href.manage(req.params.app_id)));
      return;
    }
    toast.show({ tone: 'neutral', title: `${req.summary}: not on this hub yet`, body: `${req.type} comes with the app lifecycle actions of contract §12.5 (CORE-DEPLOY). Nothing was sent.` });
  };

  if (appId) {
    const inst = installed.find((i) => i.app.id === appId);
    const removeJob = hub.actionList.find((a) => a.params.app_id === appId && a.type === 'app.remove');
    return (
      <>
        <ManageApp
          inst={inst}
          state={state}
          now={hub.now}
          isOwner={hub.canDecide !== 'no'}
          job={jobs.find((j) => j.app_id === appId && j.type === 'app.install')}
          logs={[]}
          logState={{ kind: 'error', code: 'not_available', message: 'App logs come with §12 (CORE-DEPLOY); this hub does not serve them yet.' }}
          backHref={href.installed}
          storeHref={href.app}
          onOpen={onOpen}
          onRequest={onRequest}
          onCopied={(label) => toast.show({ tone: 'ok', title: `${label} copied` })}
        />
        {removeJob && removeJob.state !== 'succeeded' && (
          <p className="om-note om-tone-info" role="status">
            Removal request: {removeJob.state.replace(/_/g, ' ')}.
          </p>
        )}
        <p className="om-hint">{REMOVE_NOTE}</p>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Installed apps" lede="Open an app, or ask to remove it. Every change is a request an owner approves." />
      <StoreTabs current="installed" />
      <InstalledList apps={installed} state={state} now={hub.now} jobs={jobs} manageHref={href.manage} onOpen={onOpen} onRequest={onRequest} onRetry={hub.reloadAll} />
      <p className="om-hint">{REMOVE_NOTE}</p>
    </>
  );
}
