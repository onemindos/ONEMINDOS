// SPDX-License-Identifier: Apache-2.0
import { useParams } from 'react-router';
import { InstalledList, PageHeader, type InstalledApp, type StoreActionRequest } from '@onemind/ui';
import { toInstalled } from '../data/adapters';
import { useHub } from '../data/hub';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';
import { loadState, StoreTabs } from './Market';
import { AppManagement } from './AppManagement';

export function Installed() {
  const hub = useHub();
  const shell = useShell();
  const { appId } = useParams();
  const state = loadState(hub.apps, hub);
  const checkedAt = hub.asOf ?? new Date(0).toISOString();
  const installed: InstalledApp[] = (hub.apps.data ?? []).filter((a) => a.installed || ['stopped', 'failed', 'unknown', 'starting', 'stopping', 'restarting', 'updating', 'configuring', 'removing'].includes(a.status)).map((a) => toInstalled(a, checkedAt));

  const onRequest = (req: StoreActionRequest) => {
    // Data deletion is a separate owner-only action, not a remove option.
    if (req.type === 'app.delete_data' || req.params.keep_data === false) return;
    void shell.requestApp(req.type, req.params.app_id);
  };
  if (appId) return <AppManagement key={appId} appId={appId} />;
  return <>
    <PageHeader title="Installed apps" lede="Open an app or review a lifecycle request. An owner approves every change." />
    <StoreTabs current="installed" />
    <InstalledList apps={installed} state={state} now={hub.now} manageHref={href.manage} onOpen={(inst) => { if (inst.url) window.open(inst.url, '_blank', 'noopener'); }} onRequest={onRequest} onRetry={hub.reloadAll} />
    <p className="om-hint">Removal keeps app data. Deleting data is a separate owner-only operation.</p>
  </>;
}
