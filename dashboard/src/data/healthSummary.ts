// SPDX-License-Identifier: Apache-2.0
// Home's health card: last backup, critical alerts, update available. Pure; every input is a
// hub answer or its absence. A missing answer is said ("not reported"), never shown as healthy.
import { formatAgo } from '../lib/time';

export type HealthTone = 'ok' | 'warn' | 'bad' | 'neutral';
export interface HealthRow { id: 'backup' | 'alerts' | 'update'; label: string; value: string; tone: HealthTone; href: string }
export interface HealthInput {
  /** GET /v1/backups/status, or undefined when it could not be read. */
  backup: Record<string, unknown> | undefined;
  /** open_alerts from GET /v1/monitoring/summary. */
  openAlerts: { critical?: number; warning?: number } | undefined;
  /** GET /v1/os/updates, or undefined when it could not be read. */
  updates: Record<string, unknown> | undefined;
  /** Hub clock (ms). */
  now: number;
}
export interface HealthLinks { backups: string; alerts: string; updates: string }

const str = (v: unknown) => (typeof v === 'string' && v ? v : undefined);

export function healthRows(i: HealthInput, links: HealthLinks): HealthRow[] {
  let backup: Pick<HealthRow, 'value' | 'tone'> = { value: 'Not reported', tone: 'neutral' };
  if (i.backup) {
    const at = str(i.backup.last_success_at);
    const t = at ? Date.parse(at) : NaN;
    const health = str(i.backup.health);
    const age = Number.isNaN(t) ? undefined : Math.max(0, Math.floor((i.now - t) / 1000));
    backup = age === undefined
      ? { value: 'No backup has finished yet', tone: 'warn' }
      : { value: `Last backup ${formatAgo(age)}`, tone: health === 'failing' || health === 'bad' ? 'bad' : health && health !== 'ok' && health !== 'healthy' ? 'warn' : 'ok' };
  }
  const crit = i.openAlerts?.critical;
  const alerts: Pick<HealthRow, 'value' | 'tone'> = crit === undefined
    ? { value: 'Not reported', tone: 'neutral' }
    : crit > 0 ? { value: `${crit} critical alert${crit === 1 ? '' : 's'} open`, tone: 'bad' } : { value: 'No critical alerts', tone: 'ok' };
  let update: Pick<HealthRow, 'value' | 'tone'> = { value: 'Not reported', tone: 'neutral' };
  if (i.updates) {
    const nodes = Array.isArray(i.updates.nodes) ? (i.updates.nodes as unknown[]) : [];
    const versions = [...new Set(nodes.map((n) => (n && typeof n === 'object' ? str((n as Record<string, unknown>).available_version) : undefined)).filter((v): v is string => !!v))];
    update = versions.length ? { value: `Update available: ${versions.join(', ')}`, tone: 'warn' } : { value: 'Up to date', tone: 'ok' };
  }
  return [
    { id: 'backup', label: 'Backups', ...backup, href: links.backups },
    { id: 'alerts', label: 'Alerts', ...alerts, href: links.alerts },
    { id: 'update', label: 'Updates', ...update, href: links.updates },
  ];
}
