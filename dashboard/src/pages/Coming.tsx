// SPDX-License-Identifier: Apache-2.0
// "Coming soon": every area whose API is not on `main` yet. Each entry names the work item that
// brings it. There are no controls and no sample data here: a placeholder that looked live would
// be a lie (PRINCIPLES P2). When an API lands, its page replaces the entry.
import { Card, PageHeader, StatusPill } from '@onemind/ui';
import { t } from '../i18n';

export interface ComingItem {
  id: string;
  title: string;
  what: string;
  /** The work item (docs/leap/STATUS.md) that delivers it. */
  need: string;
}

export const COMING_ITEMS: ComingItem[] = [
  { id: 'automation', title: 'Automation', what: 'Rules that file requests on a schedule or an event, with standing approvals you set limits on.', need: 'CORE-AUTO (/v1/automation)' },
  { id: 'files', title: 'Files', what: 'Browse, upload and share files stored on the box.', need: 'the files service (UMB-FILES)' },
  { id: 'secrets', title: 'Secrets', what: 'A vault for passwords and keys that apps and agents can be granted, one by one.', need: 'the secrets service (CORE-SECRETS)' },
  { id: 'photos', title: 'Photos', what: 'Your photo timeline, albums and trash.', need: 'UMB-PHOTO' },
  { id: 'lifecycle', title: 'Start, stop, update and delete app data', what: 'Per-app controls with progress and automatic revert when an update fails its health check.', need: 'the app lifecycle actions (CORE-APP lifecycle)' },
  { id: 'network', title: 'Network, QR and adding a device', what: 'Join codes and QR pairing, mesh state, HTTPS names for your apps.', need: 'CORE-NET / CORE-FABRIC (/v1/fabric)' },
  { id: 'storage', title: 'Storage and disk health', what: 'Disks, free space and SMART health. Reading comes first, then actions as requests.', need: 'a gateway storage route (/v1/storage); the daemon exists, the gateway does not expose it yet' },
  { id: 'backups', title: 'Backups', what: 'Where backups go, when the last one worked, and restore tests.', need: 'a gateway backups route (/v1/backups); the daemon exists, the gateway does not expose it yet' },
  { id: 'updates', title: 'Operating system updates', what: 'Current version, pending update, rollback history.', need: 'a gateway OS status route (/v1/os); the daemon exists, the gateway does not expose it yet' },
];

export function ComingCard({ item }: { item: ComingItem }) {
  return (
    <Card as="article" level={3} title={item.title} variant="sunken" aside={<StatusPill tone="neutral" label={t('coming.badge')} dot={false} />}>
      <p>{item.what}</p>
      <p className="om-hint">{t('coming.needs', { need: item.need })}</p>
    </Card>
  );
}

export function Coming() {
  return (
    <div className="dash-stack">
      <PageHeader title={t('coming.title')} lede={t('coming.lede')} />
      <ul className="dash-list" aria-label={t('coming.title')}>
        {COMING_ITEMS.map((i) => (
          <li key={i.id}>
            <ComingCard item={i} />
          </li>
        ))}
      </ul>
    </div>
  );
}
